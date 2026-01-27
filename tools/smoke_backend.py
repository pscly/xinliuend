from __future__ import annotations

import json
import time
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import select

from flow_backend.config import settings
from flow_backend.db import init_db, session_scope
from flow_backend.main import app
from flow_backend.models import User


def _redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if str(k).lower() in {"token", "accesstoken", "password", "password_hash"}:
                out[k] = "***REDACTED***"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


async def main() -> None:
    await init_db()
    print("== Settings ==")
    print("DATABASE_URL:", settings.database_url)
    print("MEMOS_BASE_URL:", settings.memos_base_url)
    print("DEV_BYPASS_MEMOS:", settings.dev_bypass_memos)
    print("MEMOS_ADMIN_TOKEN_SET:", bool(settings.memos_admin_token.strip()))
    print("CREATE_USER_ENDPOINTS:", settings.create_user_endpoints_list())
    print("CREATE_TOKEN_ENDPOINTS:", settings.create_token_endpoints_list())

    client = TestClient(app)
    # 备注：部分 Memos 部署对 username 有较严格校验（仅允许字母数字）。
    username = f"codextest{int(time.time())}"
    resp = client.post(
        settings.api_prefix + "/auth/register",
        json={"username": username, "password": "123456"},
    )
    print("\n== POST /auth/register ==")
    print("status:", resp.status_code)
    try:
        print(json.dumps(_redact(resp.json()), ensure_ascii=False, indent=2))
    except Exception:
        print(resp.text[:1200])

    async with session_scope() as session:
        user = (await session.exec(select(User).where(User.username == username))).first()
        print("\n== DB lookup ==")
        if not user:
            print("not found:", username)
        else:
            print(
                f"found: id={user.id} username={user.username} active={user.is_active} memos_id={user.memos_id} token_len={len(user.memos_token or '')}"
            )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
