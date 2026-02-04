from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from flow_backend.config import settings
from flow_backend.db import init_db, reset_engine_cache, session_scope
from flow_backend.main import app
from flow_backend.models import User
from flow_backend.security import hash_password
from flow_backend.user_session import make_user_session


def _make_async_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.anyio
async def test_cookie_auth_csrf_enforced_on_state_changing_endpoints(tmp_path: Path) -> None:
    old_db = settings.database_url
    old_secret = settings.user_session_secret
    settings.database_url = f"sqlite:///{tmp_path / 'test-cookie-auth-csrf.db'}"
    settings.user_session_secret = "test-secret"
    try:
        reset_engine_cache()
        await init_db()

        async with session_scope() as session:
            user = User(
                username="u_cookie_csrf",
                password_hash=hash_password("pass1234"),
                is_active=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        user_db_id = user.id
        assert user_db_id is not None
        user_id = int(user_db_id)

        csrf_token = "csrf-token-1"
        cookie_value = make_user_session(csrf_token=csrf_token, user_id=user_id)

        async with _make_async_client() as client:
            client.cookies.set(settings.user_session_cookie_name, cookie_value)

            # Cookie-only auth on state-changing endpoints must require CSRF.
            r = await client.put(
                "/api/v1/settings/theme",
                json={"value_json": {"dark": True}, "client_updated_at_ms": 1000},
            )
            assert r.status_code == 403
            assert r.json()["detail"] == "csrf failed"

            # Same request with CSRF header should succeed.
            r = await client.put(
                "/api/v1/settings/theme",
                json={"value_json": {"dark": True}, "client_updated_at_ms": 1000},
                headers={settings.user_csrf_header_name: csrf_token},
            )
            assert 200 <= r.status_code < 300
    finally:
        settings.database_url = old_db
        settings.user_session_secret = old_secret


@pytest.mark.anyio
async def test_me_returns_csrf_token_for_cookie_session(tmp_path: Path) -> None:
    old_db = settings.database_url
    old_secret = settings.user_session_secret
    settings.database_url = f"sqlite:///{tmp_path / 'test-cookie-me-csrf.db'}"
    settings.user_session_secret = "test-secret"
    try:
        reset_engine_cache()
        await init_db()

        async with session_scope() as session:
            user = User(
                username="u_cookie_me",
                password_hash=hash_password("pass1234"),
                is_active=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        user_db_id = user.id
        assert user_db_id is not None
        user_id = int(user_db_id)

        csrf_token = "csrf-token-me"
        cookie_value = make_user_session(csrf_token=csrf_token, user_id=user_id)

        async with _make_async_client() as client:
            client.cookies.set(settings.user_session_cookie_name, cookie_value)
            r = await client.get("/api/v1/me")
            assert r.status_code == 200
            payload = r.json()
            assert payload["code"] == 200
            assert payload["data"]["username"] == "u_cookie_me"
            assert payload["data"]["csrf_token"] == csrf_token
    finally:
        settings.database_url = old_db
        settings.user_session_secret = old_secret


@pytest.mark.anyio
async def test_logout_requires_csrf_for_valid_cookie_session_but_not_for_bearer(
    tmp_path: Path,
) -> None:
    old_db = settings.database_url
    old_secret = settings.user_session_secret
    settings.database_url = f"sqlite:///{tmp_path / 'test-cookie-logout-csrf.db'}"
    settings.user_session_secret = "test-secret"
    try:
        reset_engine_cache()
        await init_db()

        async with session_scope() as session:
            user = User(
                username="ucookielogout",
                password_hash=hash_password("pass1234"),
                memos_token="memos-token-logout",
                is_active=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        async with _make_async_client() as client:
            login = await client.post(
                "/api/v1/auth/login",
                json={"username": "ucookielogout", "password": "pass1234"},
            )
            assert login.status_code == 200
            csrf_token = login.json()["data"]["csrf_token"]

            # Cookie-session logout must require CSRF to prevent cross-site logout.
            r = await client.post("/api/v1/auth/logout")
            assert r.status_code == 403
            assert r.json()["detail"] == "csrf failed"

            r = await client.post(
                "/api/v1/auth/logout",
                headers={settings.user_csrf_header_name: csrf_token},
            )
            assert r.status_code == 200

            # Idempotent: once cookie is cleared, CSRF is not required.
            r = await client.post("/api/v1/auth/logout")
            assert r.status_code == 200

            # Bearer clients should never need CSRF for logout.
            r = await client.post(
                "/api/v1/auth/logout",
                headers={"Authorization": "Bearer definitely-not-a-real-token"},
            )
            assert r.status_code == 200
    finally:
        settings.database_url = old_db
        settings.user_session_secret = old_secret
