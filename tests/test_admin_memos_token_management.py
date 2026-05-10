from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


@dataclass
class _SettingsSnapshot:
    database_url: str
    admin_basic_user: str
    admin_basic_password: str
    admin_session_secret: str
    memos_base_url: str
    memos_admin_token: str


async def _prepare_admin_db(tmp_path: Path, db_name: str = "admin-token.db") -> _SettingsSnapshot:
    snapshot = _SettingsSnapshot(
        database_url=settings.database_url,
        admin_basic_user=settings.admin_basic_user,
        admin_basic_password=settings.admin_basic_password,
        admin_session_secret=settings.admin_session_secret,
        memos_base_url=settings.memos_base_url,
        memos_admin_token=settings.memos_admin_token,
    )
    settings.database_url = f"sqlite:///{tmp_path / db_name}"
    settings.admin_basic_user = "admin"
    settings.admin_basic_password = "pw"
    settings.admin_session_secret = "admin-secret"
    settings.memos_base_url = "https://memos.test"
    settings.memos_admin_token = "admin-token"
    reset_engine_cache()
    await init_db()
    return snapshot


def _restore_settings(snapshot: _SettingsSnapshot) -> None:
    settings.database_url = snapshot.database_url
    settings.admin_basic_user = snapshot.admin_basic_user
    settings.admin_basic_password = snapshot.admin_basic_password
    settings.admin_session_secret = snapshot.admin_session_secret
    settings.memos_base_url = snapshot.memos_base_url
    settings.memos_admin_token = snapshot.memos_admin_token


async def _create_user(
    username: str = "alice", token: str | None = "old-token", memos_id: int | None = 1
) -> User:
    async with session_scope() as session:
        user = User(
            username=username,
            password_hash=hash_password("pass1234"),
            memos_token=token,
            memos_id=memos_id,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _login_admin(client: httpx.AsyncClient) -> str:
    r = await client.post(
        "/admin/login",
        data={"username": "admin", "password": "pw", "next": "/admin"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    page = await client.get("/admin")
    assert page.status_code == 200
    marker = 'name="csrf_token" value="'
    html = page.text
    start = html.index(marker) + len(marker)
    end = html.index('"', start)
    return html[start:end]


@pytest.mark.anyio
async def test_admin_set_token_empty_input_does_not_clear_without_explicit_action(
    tmp_path: Path,
) -> None:
    snapshot = await _prepare_admin_db(tmp_path)
    try:
        user = await _create_user(token="old-token", memos_id=5)
        assert user.id is not None

        async with _make_async_client() as client:
            csrf = await _login_admin(client)
            r = await client.post(
                f"/admin/users/{user.id}/set-token",
                data={
                    "csrf_token": csrf,
                    "next": f"/admin/users/{user.id}",
                    "memos_token": "",
                    "memos_id": "",
                },
                follow_redirects=False,
            )
            assert r.status_code == 303
            assert f"/admin/users/{user.id}" in r.headers["location"]
            assert "err=" in r.headers["location"]

        async with session_scope() as session:
            row = await session.get(User, int(user.id))
            assert row is not None
            assert row.memos_token == "old-token"
            assert row.memos_id == 5
    finally:
        _restore_settings(snapshot)


@pytest.mark.anyio
async def test_admin_clear_token_requires_explicit_clear_action(tmp_path: Path) -> None:
    snapshot = await _prepare_admin_db(tmp_path)
    try:
        user = await _create_user(token="old-token", memos_id=5)
        assert user.id is not None

        async with _make_async_client() as client:
            csrf = await _login_admin(client)
            r = await client.post(
                f"/admin/users/{user.id}/set-token",
                data={
                    "csrf_token": csrf,
                    "next": f"/admin/users/{user.id}",
                    "action": "clear",
                },
                follow_redirects=False,
            )
            assert r.status_code == 303
            assert "msg=" in r.headers["location"]

        async with session_scope() as session:
            row = await session.get(User, int(user.id))
            assert row is not None
            assert row.memos_token is None
            assert row.memos_id is None
    finally:
        _restore_settings(snapshot)


@pytest.mark.anyio
async def test_admin_set_token_redirects_errors_to_next_and_keeps_existing_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = await _prepare_admin_db(tmp_path)
    try:
        user = await _create_user(username="alice", token="old-token", memos_id=1)
        await _create_user(username="bob", token="bob-token", memos_id=2)
        assert user.id is not None

        class FakeMemosClient:
            def __init__(self, **kwargs: Any) -> None:
                self.kwargs = kwargs

            async def get_current_user_with_bearer(self, token: str) -> dict[str, Any]:
                assert token == "bad-token"
                return {"username": "alice", "user_id": 9}

        monkeypatch.setattr("flow_backend.services.memos_credentials.MemosClient", FakeMemosClient)

        async with _make_async_client() as client:
            csrf = await _login_admin(client)
            next_url = f"/admin/users/{user.id}"

            r_bad_id = await client.post(
                f"/admin/users/{user.id}/set-token",
                data={
                    "csrf_token": csrf,
                    "next": next_url,
                    "action": "update",
                    "memos_token": "bad-token",
                    "memos_id": "not-number",
                },
                follow_redirects=False,
            )
            assert r_bad_id.status_code == 303
            assert r_bad_id.headers["location"].startswith(next_url)
            assert "err=" in r_bad_id.headers["location"]

            r_dup = await client.post(
                f"/admin/users/{user.id}/set-token",
                data={
                    "csrf_token": csrf,
                    "next": next_url,
                    "action": "update",
                    "memos_token": "bob-token",
                    "memos_id": "2",
                },
                follow_redirects=False,
            )
            assert r_dup.status_code == 303
            assert r_dup.headers["location"].startswith(next_url)
            assert "err=" in r_dup.headers["location"]

        async with session_scope() as session:
            row = await session.get(User, int(user.id))
            assert row is not None
            assert row.memos_token == "old-token"
            assert row.memos_id == 1
    finally:
        _restore_settings(snapshot)


@pytest.mark.anyio
async def test_admin_set_token_validates_and_saves_auto_detected_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = await _prepare_admin_db(tmp_path)
    try:
        user = await _create_user(username="alice", token="old-token", memos_id=1)
        assert user.id is not None

        class FakeMemosClient:
            def __init__(self, **kwargs: Any) -> None:
                self.kwargs = kwargs

            async def get_current_user_with_bearer(self, token: str) -> dict[str, Any]:
                assert token == "new-token"
                return {"username": "alice", "user_id": 11}

        monkeypatch.setattr("flow_backend.services.memos_credentials.MemosClient", FakeMemosClient)

        async with _make_async_client() as client:
            csrf = await _login_admin(client)
            r = await client.post(
                f"/admin/users/{user.id}/set-token",
                data={
                    "csrf_token": csrf,
                    "next": f"/admin/users/{user.id}",
                    "action": "update",
                    "memos_token": "new-token",
                },
                follow_redirects=False,
            )
            assert r.status_code == 303
            assert "msg=" in r.headers["location"]

        async with session_scope() as session:
            row = await session.get(User, int(user.id))
            assert row is not None
            assert row.memos_token == "new-token"
            assert row.memos_id == 11
    finally:
        _restore_settings(snapshot)
