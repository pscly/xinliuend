from __future__ import annotations

import json
import re
from typing import Any

import httpx

from flow_backend.config import settings


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if re.search(r"token|authorization|password|cookie", str(k), re.IGNORECASE):
                out[k] = "***REDACTED***"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(value, list):
        return [_redact(x) for x in value]
    if isinstance(value, str) and len(value) > 40 and re.search(r"eyJ|bearer|token", value, re.IGNORECASE):
        return value[:10] + "...(redacted)"
    return value


def _print(title: str, obj: Any) -> None:
    print(f"\n== {title} ==")
    print(json.dumps(_redact(obj), ensure_ascii=False, indent=2))


def _extract_token(obj: Any) -> str | None:
    # 尝试在响应里找到 “token/accessToken” 字段（不打印具体值）
    if isinstance(obj, dict):
        for k in ("accessToken", "token"):
            v = obj.get(k)
            if isinstance(v, str) and v:
                return v
        for v in obj.values():
            t = _extract_token(v)
            if t:
                return t
    if isinstance(obj, list):
        for v in obj:
            t = _extract_token(v)
            if t:
                return t
    return None


def main() -> None:
    if not settings.memos_admin_token.strip():
        print("MEMOS_ADMIN_TOKEN 为空，无法探测。")
        return

    base = settings.memos_base_url.rstrip("/")
    admin_headers = {"Authorization": f"Bearer {settings.memos_admin_token.strip()}"}

    with httpx.Client(timeout=20.0) as http:
        users_resp = http.get(f"{base}/api/v1/users", headers=admin_headers)
        users_json = users_resp.json()
        _print("GET /api/v1/users", {"status_code": users_resp.status_code, "json": users_json})

        latest = None
        for u in users_json.get("users", []):
            if isinstance(u, dict) and isinstance(u.get("name"), str) and u["name"].startswith("users/"):
                try:
                    uid = int(u["name"].split("/", 1)[1])
                except Exception:
                    continue
                if latest is None or uid > latest["id"]:
                    latest = {"id": uid, "username": u.get("username") or "", "name": u["name"]}

        if not latest or not latest["username"]:
            print("未找到可用的 latest user。")
            return

        username = str(latest["username"])
        user_id = int(latest["id"])
        print(f"\nlatest user: users/{user_id} username={username}")

        # 注意：这里只用于探测，会尝试使用固定密码 123456
        password = "123456"
        session_payload = {"passwordCredentials": {"username": username, "password": password}}
        sess = http.post(f"{base}/api/v1/auth/sessions", json=session_payload)
        sess_json = None
        try:
            sess_json = sess.json()
        except Exception:
            sess_json = {"text": sess.text[:800]}
        _print("POST /api/v1/auth/sessions", {"status_code": sess.status_code, "json": sess_json})
        print("\ncreateSession response headers (keys):")
        print(sorted(list(sess.headers.keys()))[:80])
        raw_sc = sess.headers.get("set-cookie")
        raw_auth = sess.headers.get("authorization") or sess.headers.get("grpc-metadata-authorization")
        print("has set-cookie header:", raw_sc is not None)
        print("has authorization header:", raw_auth is not None)
        if raw_sc:
            safe_sc = re.sub(r"=([^;]+)", "=***", raw_sc)
            print("\nset-cookie (masked):")
            print(safe_sc[:500])
        raw_grpc_sc = sess.headers.get("grpc-metadata-set-cookie")
        print("has grpc-metadata-set-cookie header:", raw_grpc_sc is not None)
        if raw_grpc_sc:
            safe_grpc_sc = re.sub(r"=([^;]+)", "=***", raw_grpc_sc)
            print("\ngrpc-metadata-set-cookie (masked):")
            print(safe_grpc_sc[:500])
        print("\nset-cookie cookie names:")
        try:
            for c in sess.cookies.jar:
                print(f"- {c.name} domain={c.domain} path={c.path} secure={c.secure}")
        except Exception as e:
            print("failed to read cookie jar:", e)

        token = _extract_token(sess_json)
        print("session response has token:", bool(token))

        # 1) cookies-only
        resp1 = http.post(
            f"{base}/api/v1/users/{user_id}/accessTokens",
            json={"description": "probe-session-flow"},
            cookies=sess.cookies,
        )
        _print(
            "POST /api/v1/users/{id}/accessTokens (cookies-only)",
            {"status_code": resp1.status_code, "json": resp1.json() if resp1.content else None},
        )

        # 2) bearer token, if any
        if token:
            resp2 = http.post(
                f"{base}/api/v1/users/{user_id}/accessTokens",
                json={"description": "probe-session-flow"},
                headers={"Authorization": f"Bearer {token}"},
            )
            _print(
                "POST /api/v1/users/{id}/accessTokens (bearer)",
                {"status_code": resp2.status_code, "json": resp2.json() if resp2.content else None},
            )


if __name__ == "__main__":
    main()
