from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlmodel import select

from flow_backend.config import settings
from flow_backend.db import init_db, reset_engine_cache, session_scope
from flow_backend.main import app
from flow_backend.models import User
from flow_backend.security import hash_password
from flow_backend.user_session import make_user_session


def _make_async_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@dataclass
class _SettingsSnapshot:
    database_url: str
    user_session_secret: str
    dev_bypass_memos: bool
    memos_base_url: str
    memos_admin_token: str
    memos_http_trust_env: bool


async def _prepare_db(tmp_path: Path, db_name: str = "memos-credential.db") -> _SettingsSnapshot:
    snapshot = _SettingsSnapshot(
        database_url=settings.database_url,
        user_session_secret=settings.user_session_secret,
        dev_bypass_memos=settings.dev_bypass_memos,
        memos_base_url=settings.memos_base_url,
        memos_admin_token=settings.memos_admin_token,
        memos_http_trust_env=settings.memos_http_trust_env,
    )
    settings.database_url = f"sqlite:///{tmp_path / db_name}"
    settings.user_session_secret = "test-user-session-secret"
    settings.dev_bypass_memos = False
    settings.memos_base_url = "https://memos.test"
    settings.memos_admin_token = "admin-token"
    settings.memos_http_trust_env = False
    reset_engine_cache()
    await init_db()
    return snapshot


def _restore_settings(snapshot: _SettingsSnapshot) -> None:
    settings.database_url = snapshot.database_url
    settings.user_session_secret = snapshot.user_session_secret
    settings.dev_bypass_memos = snapshot.dev_bypass_memos
    settings.memos_base_url = snapshot.memos_base_url
    settings.memos_admin_token = snapshot.memos_admin_token
    settings.memos_http_trust_env = snapshot.memos_http_trust_env


async def _create_user(
    *,
    username: str,
    password: str = "pass1234",
    token: str | None = "old-token",
    memos_id: int | None = 1,
    memos_user_name: str | None = None,
    is_admin: bool = False,
) -> User:
    async with session_scope() as session:
        user = User(
            username=username,
            password_hash=hash_password(password),
            memos_id=memos_id,
            memos_user_name=memos_user_name,
            memos_token=token,
            is_active=True,
            is_admin=is_admin,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.mark.anyio
async def test_get_memos_credential_returns_safe_status(tmp_path: Path) -> None:
    snapshot = await _prepare_db(tmp_path)
    try:
        await _create_user(
            username="alice", token="memos_pat_abcdefghijklmnopqrstuvwxyz", memos_id=7, memos_user_name="users/7"
        )

        async with _make_async_client() as client:
            r = await client.get(
                "/api/v1/me/memos-credential",
                headers={"Authorization": "Bearer memos_pat_abcdefghijklmnopqrstuvwxyz"},
            )
            assert r.status_code == 200
            data = r.json()
            assert data["memos_base_url"] == "https://memos.test"
            assert data["has_token"] is True
            assert data["token_preview"].startswith("memos_pa")
            assert "abcdefghijklmnopqrstuvwxyz" not in data["token_preview"]
            assert data["memos_user_id"] == 7
            assert data["memos_user_name"] == "users/7"
            assert data["can_auto_issue_token"] is True
            assert "token" not in data
    finally:
        _restore_settings(snapshot)


@pytest.mark.anyio
async def test_put_memos_credential_token_validates_owner_and_rotates_bearer_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = await _prepare_db(tmp_path)
    try:
        await _create_user(username="alice", token="old-token", memos_id=1)

        class FakeMemosClient:
            def __init__(self, **kwargs: Any) -> None:
                self.kwargs = kwargs

            async def get_current_user_with_bearer(self, token: str) -> dict[str, Any]:
                assert token == "new-token"
                return {"username": "alice", "user_id": 42, "name": "users/42"}

        monkeypatch.setattr("flow_backend.services.memos_credentials.MemosClient", FakeMemosClient)

        async with _make_async_client() as client:
            r = await client.put(
                "/api/v1/me/memos-credential/token",
                json={"memos_token": "  new-token  "},
                headers={"Authorization": "Bearer old-token"},
            )
            assert r.status_code == 200
            data = r.json()
            assert data["ok"] is True
            assert data["token"] == "new-token"
            assert data["server_url"] == "https://memos.test"
            assert data["memos_user_id"] == 42
            assert data["memos_user_name"] == "users/42"
            assert data["memos_username"] == "alice"
            assert data["csrf_token"] is None
            assert data["token_preview"] != "new-token"

            r_old = await client.get("/api/v1/me", headers={"Authorization": "Bearer old-token"})
            assert r_old.status_code == 401
            r_new = await client.get("/api/v1/me", headers={"Authorization": "Bearer new-token"})
            assert r_new.status_code == 200

        async with session_scope() as session:
            row = (await session.exec(select(User).where(User.username == "alice"))).first()
            assert row is not None
            assert row.memos_token == "new-token"
            assert row.memos_id == 42
    finally:
        _restore_settings(snapshot)


@pytest.mark.anyio
async def test_put_memos_credential_token_rejects_empty_username_mismatch_and_id_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = await _prepare_db(tmp_path)
    try:
        await _create_user(username="alice", token="old-token", memos_id=1)

        async with _make_async_client() as client:
            r = await client.put(
                "/api/v1/me/memos-credential/token",
                json={"memos_token": "   "},
                headers={"Authorization": "Bearer old-token"},
            )
            assert r.status_code == 422

        class FakeMismatchClient:
            def __init__(self, **kwargs: Any) -> None:
                self.kwargs = kwargs

            async def get_current_user_with_bearer(self, token: str) -> dict[str, Any]:  # noqa: ARG002
                return {"username": "bob", "user_id": 2, "name": "users/2"}

        monkeypatch.setattr(
            "flow_backend.services.memos_credentials.MemosClient", FakeMismatchClient
        )
        async with _make_async_client() as client:
            r = await client.put(
                "/api/v1/me/memos-credential/token",
                json={"memos_token": "bob-token"},
                headers={"Authorization": "Bearer old-token"},
            )
            assert r.status_code == 403
            assert "username" in r.json()["message"].lower()

        class FakeIdClient:
            def __init__(self, **kwargs: Any) -> None:
                self.kwargs = kwargs

            async def get_current_user_with_bearer(self, token: str) -> dict[str, Any]:  # noqa: ARG002
                return {"username": "alice", "user_id": 3, "name": "users/3"}

        monkeypatch.setattr("flow_backend.services.memos_credentials.MemosClient", FakeIdClient)
        async with _make_async_client() as client:
            r = await client.put(
                "/api/v1/me/memos-credential/token",
                json={"memos_token": "alice-token", "memos_user_id": 4},
                headers={"Authorization": "Bearer old-token"},
            )
            assert r.status_code == 400
            assert "memos_user_id" in r.json()["message"]

        async with session_scope() as session:
            row = (await session.exec(select(User).where(User.username == "alice"))).first()
            assert row is not None
            assert row.memos_token == "old-token"
            assert row.memos_id == 1
    finally:
        _restore_settings(snapshot)


@pytest.mark.anyio
async def test_issue_memos_credential_token_verifies_current_password_and_saves_pat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = await _prepare_db(tmp_path)
    try:
        await _create_user(username="alice", password="pass1234", token="old-token", memos_id=1)
        calls: list[tuple[str, Any]] = []

        class FakeMemosClient:
            def __init__(self, **kwargs: Any) -> None:
                self.kwargs = kwargs

            async def sign_in_with_password(
                self, username: str, app_password: str
            ) -> dict[str, Any]:
                calls.append(("signin", username, app_password))
                return {"access_token": "signin-token", "username": "alice", "user_id": 42, "name": "users/42"}

            async def create_personal_access_token_with_bearer(
                self,
                user_name: str,
                bearer_token: str,
                description: str,
                expires_in_days: int = 0,
            ) -> str:
                calls.append(("pat", user_name, bearer_token, description, expires_in_days))
                return "new-pat-token"

        monkeypatch.setattr("flow_backend.services.memos_credentials.MemosClient", FakeMemosClient)

        async with _make_async_client() as client:
            r_wrong = await client.post(
                "/api/v1/me/memos-credential/issue-token",
                json={"current_password": "wrong"},
                headers={"Authorization": "Bearer old-token"},
            )
            assert r_wrong.status_code == 401

            r = await client.post(
                "/api/v1/me/memos-credential/issue-token",
                json={"current_password": "pass1234"},
                headers={"Authorization": "Bearer old-token"},
            )
            assert r.status_code == 200
            data = r.json()
            assert data["token"] == "new-pat-token"
            assert data["memos_user_id"] == 42
            assert data["memos_user_name"] == "users/42"
            assert data["memos_username"] == "alice"

        assert calls[0] == ("signin", "alice", "pass1234")
        assert calls[1][0] == "pat"

        async with session_scope() as session:
            row = (await session.exec(select(User).where(User.username == "alice"))).first()
            assert row is not None
            assert row.memos_token == "new-pat-token"
            assert row.memos_id == 42
    finally:
        _restore_settings(snapshot)


@pytest.mark.anyio
async def test_issue_memos_credential_token_upstream_failure_does_not_change_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = await _prepare_db(tmp_path)
    try:
        await _create_user(username="alice", password="pass1234", token="old-token", memos_id=1)

        from flow_backend.memos_client import MemosClientError

        class BrokenMemosClient:
            def __init__(self, **kwargs: Any) -> None:
                self.kwargs = kwargs

            async def sign_in_with_password(
                self, username: str, app_password: str
            ) -> dict[str, Any]:  # noqa: ARG002
                raise MemosClientError("memos down")

        monkeypatch.setattr(
            "flow_backend.services.memos_credentials.MemosClient", BrokenMemosClient
        )

        async with _make_async_client() as client:
            r = await client.post(
                "/api/v1/me/memos-credential/issue-token",
                json={"current_password": "pass1234"},
                headers={"Authorization": "Bearer old-token"},
            )
            assert r.status_code == 502

        async with session_scope() as session:
            row = (await session.exec(select(User).where(User.username == "alice"))).first()
            assert row is not None
            assert row.memos_token == "old-token"
            assert row.memos_id == 1
    finally:
        _restore_settings(snapshot)


@pytest.mark.anyio
async def test_memos_token_unique_index_blocks_duplicate_non_null_and_allows_nulls(
    tmp_path: Path,
) -> None:
    snapshot = await _prepare_db(tmp_path)
    try:
        async with session_scope() as session:
            session.add(User(username="u1", password_hash="x", memos_token=None, is_active=True))
            session.add(User(username="u2", password_hash="x", memos_token=None, is_active=True))
            session.add(User(username="u3", password_hash="x", memos_token="same", is_active=True))
            await session.commit()

            session.add(User(username="u4", password_hash="x", memos_token="same", is_active=True))
            with pytest.raises(Exception):
                await session.commit()
            await session.rollback()

            rows = (await session.exec(text("PRAGMA index_list('users')"))).all()
            index_names = {str(row[1]) for row in rows}
            assert "uq_users_memos_token_not_null" in index_names
    finally:
        _restore_settings(snapshot)


@pytest.mark.anyio
async def test_cookie_session_credential_update_returns_rotated_csrf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = await _prepare_db(tmp_path)
    try:
        user = await _create_user(username="alice", token="old-token", memos_id=1)
        assert user.id is not None
        csrf_token = "csrf-old"

        class FakeMemosClient:
            def __init__(self, **kwargs: Any) -> None:
                self.kwargs = kwargs

            async def get_current_user_with_bearer(self, token: str) -> dict[str, Any]:
                assert token == "new-token"
                return {"username": "alice", "user_id": 2, "name": "users/2"}

        monkeypatch.setattr("flow_backend.services.memos_credentials.MemosClient", FakeMemosClient)

        async with _make_async_client() as client:
            client.cookies.set(
                settings.user_session_cookie_name,
                make_user_session(user_id=int(user.id), csrf_token=csrf_token),
            )
            r_missing_csrf = await client.put(
                "/api/v1/me/memos-credential/token",
                json={"memos_token": "new-token"},
            )
            assert r_missing_csrf.status_code == 403

            r = await client.put(
                "/api/v1/me/memos-credential/token",
                json={"memos_token": "new-token"},
                headers={settings.user_csrf_header_name: csrf_token},
            )
            assert r.status_code == 200
            data = r.json()
            assert data["token"] == "new-token"
            assert isinstance(data["csrf_token"], str)
            assert data["csrf_token"] != csrf_token

            r2 = await client.get("/api/v1/me")
            assert r2.status_code == 200
            assert r2.json()["csrf_token"] == data["csrf_token"]
    finally:
        _restore_settings(snapshot)
