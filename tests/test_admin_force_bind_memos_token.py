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
class _Snapshot:
    database_url: str
    admin_basic_user: str
    admin_basic_password: str
    admin_session_secret: str
    memos_base_url: str
    memos_admin_token: str


async def _setup(tmp_path: Path) -> _Snapshot:
    snap = _Snapshot(
        database_url=settings.database_url,
        admin_basic_user=settings.admin_basic_user,
        admin_basic_password=settings.admin_basic_password,
        admin_session_secret=settings.admin_session_secret,
        memos_base_url=settings.memos_base_url,
        memos_admin_token=settings.memos_admin_token,
    )
    settings.database_url = f"sqlite:///{tmp_path / 'force-bind.db'}"
    settings.admin_basic_user = "admin"
    settings.admin_basic_password = "pw"
    settings.admin_session_secret = "admin-secret"
    settings.memos_base_url = "https://memos.test"
    settings.memos_admin_token = "admin-token"
    reset_engine_cache()
    await init_db()
    return snap


def _restore(snap: _Snapshot) -> None:
    settings.database_url = snap.database_url
    settings.admin_basic_user = snap.admin_basic_user
    settings.admin_basic_password = snap.admin_basic_password
    settings.admin_session_secret = snap.admin_session_secret
    settings.memos_base_url = snap.memos_base_url
    settings.memos_admin_token = snap.memos_admin_token


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


async def _seed_user(username: str = "pscly") -> int:
    async with session_scope() as session:
        u = User(
            username=username,
            password_hash=hash_password("pw123456"),
            memos_id=1,
            memos_token="legacy-jwt-that-no-longer-works",
            is_active=True,
        )
        session.add(u)
        await session.commit()
        await session.refresh(u)
        assert u.id is not None
        return int(u.id)


@pytest.mark.anyio
async def test_force_bind_skips_memos_validation_and_writes_pat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Admin force=1 must NOT call Memos at all — that's the whole point of the
    escape hatch when the upstream identity endpoint is broken."""

    snap = await _setup(tmp_path)
    try:
        user_id = await _seed_user("pscly")

        validation_calls: list[str] = []

        class ExplodingClient:
            def __init__(self, **kwargs: Any) -> None:
                pass

            async def get_current_user_with_bearer(self, token: str) -> dict[str, Any]:
                validation_calls.append(token)
                raise AssertionError("force=1 must not invoke Memos validation")

        monkeypatch.setattr(
            "flow_backend.services.memos_credentials.MemosClient",
            ExplodingClient,
        )

        async with _make_async_client() as client:
            csrf = await _login_admin(client)
            r = await client.post(
                f"/admin/users/{user_id}/set-token",
                data={
                    "csrf_token": csrf,
                    "next": f"/admin/users/{user_id}",
                    "action": "update",
                    "memos_token": "memos_pat_brand_new_pat_for_pscly",
                    "force": "1",
                },
                follow_redirects=False,
            )
            assert r.status_code == 303
            loc = r.headers["location"]
            assert loc.startswith(f"/admin/users/{user_id}")
            assert "msg=" in loc
            # The redirect text must clearly mark the write as un-validated.
            assert "%E5%BC%BA%E5%88%B6" in loc or "强制" in loc

        async with session_scope() as session:
            row = await session.get(User, user_id)
            assert row is not None
            assert row.memos_token == "memos_pat_brand_new_pat_for_pscly"

        assert validation_calls == []
    finally:
        _restore(snap)


@pytest.mark.anyio
async def test_normal_path_still_validates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When force is absent, the normal validate-then-save path must still run."""

    snap = await _setup(tmp_path)
    try:
        user_id = await _seed_user("alice")

        calls: list[str] = []

        class FakeClient:
            def __init__(self, **kwargs: Any) -> None:
                pass

            async def get_current_user_with_bearer(self, token: str) -> dict[str, Any]:
                calls.append(token)
                # Simulate new-style Memos with no numeric id.
                return {"username": "alice", "user_id": 0, "name": "users/alice"}

        monkeypatch.setattr(
            "flow_backend.services.memos_credentials.MemosClient",
            FakeClient,
        )

        async with _make_async_client() as client:
            csrf = await _login_admin(client)
            r = await client.post(
                f"/admin/users/{user_id}/set-token",
                data={
                    "csrf_token": csrf,
                    "next": f"/admin/users/{user_id}",
                    "action": "update",
                    "memos_token": "memos_pat_alice",
                },
                follow_redirects=False,
            )
            assert r.status_code == 303
            assert "msg=" in r.headers["location"]

        async with session_scope() as session:
            row = await session.get(User, user_id)
            assert row is not None
            assert row.memos_token == "memos_pat_alice"

        # Memos was hit exactly once for validation.
        assert calls == ["memos_pat_alice"]
    finally:
        _restore(snap)


@pytest.mark.anyio
async def test_force_bind_token_already_used_by_other_user_is_rejected(
    tmp_path: Path,
) -> None:
    """Even force-bind must not silently overwrite another user's token."""

    snap = await _setup(tmp_path)
    try:
        alice = await _seed_user("alice")
        async with session_scope() as session:
            bob = User(
                username="bob",
                password_hash=hash_password("pw123456"),
                memos_id=2,
                memos_token="bob-pat",
                is_active=True,
            )
            session.add(bob)
            await session.commit()

        async with _make_async_client() as client:
            csrf = await _login_admin(client)
            r = await client.post(
                f"/admin/users/{alice}/set-token",
                data={
                    "csrf_token": csrf,
                    "next": f"/admin/users/{alice}",
                    "action": "update",
                    "memos_token": "bob-pat",  # Already used by bob.
                    "force": "1",
                },
                follow_redirects=False,
            )
            assert r.status_code == 303
            assert "err=" in r.headers["location"]

        async with session_scope() as session:
            row = await session.get(User, alice)
            assert row is not None
            assert row.memos_token == "legacy-jwt-that-no-longer-works"
    finally:
        _restore(snap)
