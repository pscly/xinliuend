from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from flow_backend.config import settings
from flow_backend.db import init_db, reset_engine_cache, session_scope
from flow_backend.main import app
from flow_backend.memos_client import MemosUserAndToken
from flow_backend.models import User
from flow_backend.security import hash_password


def _make_async_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _fake_memos_client_factory(token: str, user_id: int = 123):
    class FakeMemosClient:
        def __init__(self, base_url: str, admin_token: str, timeout_seconds: float) -> None:
            self.base_url = base_url
            self.admin_token = admin_token
            self.timeout_seconds = timeout_seconds

        async def create_access_token_from_login(self, username: str, password: str):
            return MemosUserAndToken(memos_user_id=user_id, memos_token=token)

    return FakeMemosClient


@pytest.mark.anyio
async def test_login_memos_creates_user_and_then_normal_login_works(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    settings.database_url = f"sqlite:///{tmp_path / 'test-auth.db'}"
    reset_engine_cache()
    await init_db()

    import flow_backend.routers.auth as auth_router

    monkeypatch.setattr(auth_router, "MemosClient", _fake_memos_client_factory(token="tok-memos-1", user_id=7))

    async with _make_async_client() as client:
        r = await client.post("/api/v1/auth/login_memos", json={"username": "u1", "password": "pw123456"})
        assert r.status_code == 200
        assert r.json()["data"]["token"] == "tok-memos-1"

        # 走本地 /login（校验本地密码哈希 + 直接返回已存 token）
        r = await client.post("/api/v1/auth/login", json={"username": "u1", "password": "pw123456"})
        assert r.status_code == 200
        assert r.json()["data"]["token"] == "tok-memos-1"


@pytest.mark.anyio
async def test_login_memos_updates_existing_user_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    settings.database_url = f"sqlite:///{tmp_path / 'test-auth2.db'}"
    reset_engine_cache()
    await init_db()

    async with session_scope() as session:
        session.add(
            User(
                username="u2",
                password_hash=hash_password("oldpass"),
                memos_id=1,
                memos_token="tok-old",
                is_active=True,
            )
        )
        await session.commit()

    import flow_backend.routers.auth as auth_router

    monkeypatch.setattr(auth_router, "MemosClient", _fake_memos_client_factory(token="tok-new", user_id=99))

    async with _make_async_client() as client:
        r = await client.post("/api/v1/auth/login_memos", json={"username": "u2", "password": "newpass"})
        assert r.status_code == 200
        assert r.json()["data"]["token"] == "tok-new"

        # 再次 /login 应返回新 token（并且使用新密码）
        r = await client.post("/api/v1/auth/login", json={"username": "u2", "password": "newpass"})
        assert r.status_code == 200
        assert r.json()["data"]["token"] == "tok-new"


@pytest.mark.anyio
async def test_login_memos_denies_disabled_user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    settings.database_url = f"sqlite:///{tmp_path / 'test-auth3.db'}"
    reset_engine_cache()
    await init_db()

    async with session_scope() as session:
        session.add(
            User(
                username="u3",
                password_hash=hash_password("pass1234"),
                memos_id=3,
                memos_token="tok-3",
                is_active=False,
            )
        )
        await session.commit()

    import flow_backend.routers.auth as auth_router

    monkeypatch.setattr(auth_router, "MemosClient", _fake_memos_client_factory(token="tok-should-not-happen"))

    async with _make_async_client() as client:
        r = await client.post("/api/v1/auth/login_memos", json={"username": "u3", "password": "whatever"})
        assert r.status_code == 403

