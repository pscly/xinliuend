from __future__ import annotations

import argparse
import json
import re
from typing import Any

import httpx
from fastapi.testclient import TestClient
from sqlmodel import select

from flow_backend.config import settings
from flow_backend.db import session_scope
from flow_backend.main import app
from flow_backend.models import User


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if re.search(r"token|authorization|password", str(k), re.IGNORECASE):
                out[k] = "***REDACTED***"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(value, list):
        return [_redact(x) for x in value]
    if isinstance(value, str) and len(value) > 160 and re.search(r"token|bearer|eyJ", value):
        return value[:12] + "...(redacted)"
    return value


def _print_json(title: str, obj: Any) -> None:
    print(f"\n== {title} ==")
    print(json.dumps(_redact(obj), ensure_ascii=False, indent=2))


def _http_summary(resp: httpx.Response) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "status_code": resp.status_code,
        "headers": {"content-type": resp.headers.get("content-type")},
    }
    try:
        summary["json"] = resp.json()
    except Exception:
        summary["text"] = resp.text[:1200]
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="探测 Memos API（默认只读；--write 才会执行 POST 探测）")
    parser.add_argument("--write", action="store_true", help="允许执行 POST 探测（可能会创建 token）")
    args = parser.parse_args()

    print("== Settings ==")
    print("DATABASE_URL:", settings.database_url)
    print("MEMOS_BASE_URL:", settings.memos_base_url)
    print("DEV_BYPASS_MEMOS:", settings.dev_bypass_memos)
    print("MEMOS_ADMIN_TOKEN_SET:", bool(settings.memos_admin_token.strip()))
    print("CREATE_USER_ENDPOINTS:", settings.create_user_endpoints_list())
    print("CREATE_TOKEN_ENDPOINTS:", settings.create_token_endpoints_list())

    # Admin page smoke check (template rendering)
    client = TestClient(app)
    r = client.get("/admin", auth=(settings.admin_basic_user, settings.admin_basic_password))
    print("\n== FastAPI /admin ==")
    print("status:", r.status_code, "len:", len(r.text))
    print(r.text[:300])

    # DB check
    import asyncio

    async def _db_check() -> None:
        async with session_scope() as session:
            users = list(await session.exec(select(User).order_by(User.id.desc()).limit(5)))
            print("\n== DB users (top 5) ==")
            print("count(top5):", len(users))
            for u in users:
                print(
                    f"- id={u.id} username={u.username} active={u.is_active} memos_id={u.memos_id} token_len={len(u.memos_token or '')}"
                )

    asyncio.run(_db_check())

    # Memos probe（尽量只读；少量 POST 仅用于探测接口形状）
    if not settings.memos_admin_token.strip():
        print("\n== Memos probe skipped (MEMOS_ADMIN_TOKEN empty) ==")
        return

    base = settings.memos_base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {settings.memos_admin_token.strip()}"}

    candidates: list[tuple[str, str, Any]] = [
        ("GET", f"{base}/api/v1/users", None),
        ("GET", f"{base}/api/v1/user", None),
        ("GET", f"{base}/api/v1/me", None),
        ("GET", f"{base}/api/v1/status", None),
        ("GET", f"{base}/api/v1/system/status", None),
        ("GET", f"{base}/api/v1/accessTokens", None),
        ("GET", f"{base}/api/v1/users/1/accessTokens", None),
        ("GET", f"{base}/api/v1/users/1/accessToken", None),
    ]

    auth_probe: list[tuple[str, str, Any]] = [
        ("POST", f"{base}/api/v1/auth/sessions", {"passwordCredentials": {"username": "dummy", "password": "dummy"}}),
        ("GET", f"{base}/api/v1/auth/sessions/current", None),
        ("DELETE", f"{base}/api/v1/auth/sessions/current", None),
    ]

    with httpx.Client(timeout=15.0) as http:
        users_payload: dict[str, Any] | None = None

        for method, url, payload in candidates:
            try:
                resp = http.request(method, url, headers=headers, json=payload)
                summary = _http_summary(resp)
                _print_json(f"Memos {method} {url}", summary)
                if method == "GET" and url.endswith("/api/v1/users") and isinstance(summary.get("json"), dict):
                    users_payload = summary["json"]
            except Exception as e:
                _print_json(f"Memos {method} {url}", {"error": str(e)})

        if args.write:
            write_candidates = [
                ("POST", f"{base}/api/v1/users/1/accessTokens", {"name": "codex-probe"}),
                ("POST", f"{base}/api/v1/users/1/accessTokens", {"description": "codex-probe"}),
                ("POST", f"{base}/api/v1/users/1/accessTokens", {"accessToken": {"name": "codex-probe"}}),
                ("POST", f"{base}/api/v1/users/1/accessTokens", {"accessToken": {"description": "codex-probe"}}),
                ("POST", f"{base}/api/v1/users/1/accessTokens", {"name": "codex-probe", "expiresAt": 0}),
                ("POST", f"{base}/api/v1/users/1/accessTokens", {"accessToken": {"description": "codex-probe", "expiresAt": 0}}),
            ]
            for method, url, payload in write_candidates:
                try:
                    resp = http.request(method, url, headers=headers, json=payload)
                    _print_json(f"Memos(write) {method} {url}", _http_summary(resp))
                except Exception as e:
                    _print_json(f"Memos(write) {method} {url}", {"error": str(e)})

        # Auth endpoints probe：不携带 admin token，避免误判权限问题
        for method, url, payload in auth_probe:
            try:
                resp = http.request(method, url, json=payload)
                _print_json(f"Memos(auth) {method} {url}", _http_summary(resp))
            except Exception as e:
                _print_json(f"Memos(auth) {method} {url}", {"error": str(e)})

        # 额外探测：尝试对“最新创建的用户”生成 Token，观察权限错误信息（常见 403）。
        latest_user_id: int | None = None
        if isinstance(users_payload, dict) and isinstance(users_payload.get("users"), list):
            for u in users_payload["users"]:
                if isinstance(u, dict):
                    name = u.get("name")
                    if isinstance(name, str) and name.startswith("users/"):
                        try:
                            latest_user_id = max(latest_user_id or 0, int(name.split("/", 1)[1]))
                        except Exception:
                            pass

        if latest_user_id and latest_user_id != 1:
            url = f"{base}/api/v1/users/{latest_user_id}/accessTokens"
            if args.write:
                try:
                    resp = http.post(url, headers=headers, json={"description": "codex-probe-latest"})
                    _print_json(f"Memos(write) POST {url} (latest user)", _http_summary(resp))
                except Exception as e:
                    _print_json(f"Memos(write) POST {url} (latest user)", {"error": str(e)})


if __name__ == "__main__":
    main()
