from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlmodel import select

from flow_backend.config import settings
from flow_backend.db import init_db, reset_engine_cache, session_scope
from flow_backend.main import app
from flow_backend.models import User
from flow_backend.password_crypto import decrypt_password
from flow_backend.security import hash_password, verify_password
from flow_backend.user_session import make_user_session


def _make_async_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.anyio
async def test_change_password_cookie_session_rotates_csrf_and_persists_encrypted_password(
    tmp_path: Path,
) -> None:
    old_db = settings.database_url
    old_secret = settings.user_session_secret
    old_bypass = settings.dev_bypass_memos
    old_key = settings.user_password_encryption_key
    settings.database_url = f"sqlite:///{tmp_path / 'test-change-password.db'}"
    settings.user_session_secret = "test-secret"
    settings.dev_bypass_memos = True
    settings.user_password_encryption_key = "WmfpBBPjCEIb_IJvZP_t6aG9AZ51qHm_iNg0Q_y6Bno="
    try:
        reset_engine_cache()
        await init_db()

        async with session_scope() as session:
            user = User(
                username="u_change_pw",
                password_hash=hash_password("oldpass123"),
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

            # Missing CSRF must be rejected for cookie-session write endpoints.
            r = await client.post(
                "/api/v1/me/password",
                json={
                    "current_password": "oldpass123",
                    "new_password": "newpass456",
                    "new_password2": "newpass456",
                },
            )
            assert r.status_code == 403
            assert r.json()["detail"] == "csrf failed"

            # Wrong current password.
            r = await client.post(
                "/api/v1/me/password",
                json={
                    "current_password": "wrong",
                    "new_password": "newpass456",
                    "new_password2": "newpass456",
                },
                headers={settings.user_csrf_header_name: csrf_token},
            )
            assert r.status_code == 401

            # Password mismatch.
            r = await client.post(
                "/api/v1/me/password",
                json={
                    "current_password": "oldpass123",
                    "new_password": "newpass456",
                    "new_password2": "newpass789",
                },
                headers={settings.user_csrf_header_name: csrf_token},
            )
            assert r.status_code == 400
            assert r.json()["detail"] == "password mismatch"

            # Success should rotate CSRF and update cookie.
            r = await client.post(
                "/api/v1/me/password",
                json={
                    "current_password": "oldpass123",
                    "new_password": "newpass456",
                    "new_password2": "newpass456",
                },
                headers={settings.user_csrf_header_name: csrf_token},
            )
            assert r.status_code == 200
            payload = r.json()
            assert payload["code"] == 200
            new_csrf = payload["data"]["csrf_token"]
            assert isinstance(new_csrf, str)
            assert new_csrf != csrf_token

            # /me should return the rotated CSRF from the new cookie session.
            r2 = await client.get("/api/v1/me")
            assert r2.status_code == 200
            assert r2.json()["data"]["csrf_token"] == new_csrf

        async with session_scope() as session:
            row = (await session.exec(select(User).where(User.id == user_id))).first()
            assert row is not None
            assert verify_password("newpass456", row.password_hash)
            assert row.password_enc
            assert decrypt_password(row.password_enc) == "newpass456"
    finally:
        settings.database_url = old_db
        settings.user_session_secret = old_secret
        settings.dev_bypass_memos = old_bypass
        settings.user_password_encryption_key = old_key

