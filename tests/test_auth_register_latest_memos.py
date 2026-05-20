from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlmodel import select

from flow_backend.config import settings
from flow_backend.db import init_db, reset_engine_cache, session_scope
from flow_backend.main import app
from flow_backend.models import User


def _make_async_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.anyio
async def test_register_persists_latest_memos_user_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_db = settings.database_url
    old_bypass = settings.dev_bypass_memos
    old_base = settings.memos_base_url
    old_token = settings.memos_admin_token
    old_trust_env = settings.memos_http_trust_env
    settings.database_url = f"sqlite:///{tmp_path / 'test-auth-register-latest.db'}"
    settings.dev_bypass_memos = False
    settings.memos_base_url = "https://memos.test"
    settings.memos_admin_token = "admin-token"
    settings.memos_http_trust_env = False
    reset_engine_cache()
    await init_db()

    class FakeCreateResult:
        memos_user_id = None
        memos_user_name = "users/alice"
        memos_token = "pat-alice"

    class FakeMemosClient:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs
            assert kwargs["trust_env"] is False

        async def create_user_and_token(self, **kwargs: Any) -> FakeCreateResult:
            assert kwargs["username"] == "alice"
            assert kwargs["password"] == "pass1234"
            return FakeCreateResult()

    monkeypatch.setattr("flow_backend.routers.auth.MemosClient", FakeMemosClient)

    try:
        async with _make_async_client() as client:
            r = await client.post(
                "/api/v1/auth/register",
                json={"username": "alice", "password": "pass1234"},
            )
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["token"] == "pat-alice"
            assert data["server_url"] == "https://memos.test"
            assert isinstance(data["csrf_token"], str) and data["csrf_token"]

        async with session_scope() as session:
            row = (await session.exec(select(User).where(User.username == "alice"))).first()
            assert row is not None
            assert row.memos_token == "pat-alice"
            assert row.memos_user_name == "users/alice"
            assert row.memos_id is None
    finally:
        settings.database_url = old_db
        settings.dev_bypass_memos = old_bypass
        settings.memos_base_url = old_base
        settings.memos_admin_token = old_token
        settings.memos_http_trust_env = old_trust_env
