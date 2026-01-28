from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from flow_backend.config import settings
from flow_backend.db import init_db, reset_engine_cache, session_scope
from flow_backend.main import app
from flow_backend.models import User
from flow_backend.security import hash_password


def _make_async_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.anyio
async def test_login_requires_memos_token(tmp_path: Path):
    settings.database_url = f"sqlite:///{tmp_path / 'test-auth-login.db'}"
    reset_engine_cache()
    await init_db()

    async with session_scope() as session:
        session.add(
            User(
                username="u1",
                password_hash=hash_password("pass1234"),
                memos_id=None,
                memos_token=None,
                is_active=True,
            )
        )
        await session.commit()

    async with _make_async_client() as client:
        r = await client.post("/api/v1/auth/login", json={"username": "u1", "password": "pass1234"})
        assert r.status_code == 409
