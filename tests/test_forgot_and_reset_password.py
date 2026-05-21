from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlmodel import select

from flow_backend.config import settings
from flow_backend.db import init_db, reset_engine_cache, session_scope
from flow_backend.main import app
from flow_backend.models import PasswordResetToken, User, utc_now
from flow_backend.security import hash_password, verify_password
from flow_backend.services import password_reset_service, site_settings_service


def _make_async_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _bootstrap(tmp_path: Path, db_name: str) -> dict[str, Any]:
    snap = {
        "database_url": settings.database_url,
        "user_password_encryption_key": settings.user_password_encryption_key,
        "dev_bypass_memos": settings.dev_bypass_memos,
        "public_base_url": settings.public_base_url,
        "auth_forgot_password_rate_limit_per_ip": settings.auth_forgot_password_rate_limit_per_ip,
        "auth_reset_password_rate_limit_per_ip": settings.auth_reset_password_rate_limit_per_ip,
    }
    settings.database_url = f"sqlite:///{tmp_path / db_name}"
    settings.user_password_encryption_key = "WmfpBBPjCEIb_IJvZP_t6aG9AZ51qHm_iNg0Q_y6Bno="
    settings.dev_bypass_memos = True
    settings.public_base_url = "https://xl.test"
    settings.auth_forgot_password_rate_limit_per_ip = 50
    settings.auth_reset_password_rate_limit_per_ip = 50
    reset_engine_cache()
    site_settings_service.invalidate_cache()
    await init_db()
    return snap


def _restore(snap: dict[str, Any]) -> None:
    for k, v in snap.items():
        setattr(settings, k, v)
    site_settings_service.invalidate_cache()


async def _create_verified_user(username: str = "pscly", email: str = "pscly1@163.com") -> int:
    async with session_scope() as session:
        u = User(
            username=username,
            password_hash=hash_password("oldpass1"),
            memos_token=f"tok-{username}",
            memos_id=1,
            is_active=True,
            email=email,
            email_verified_at=utc_now(),
        )
        session.add(u)
        await session.commit()
        await session.refresh(u)
        assert u.id is not None
        return int(u.id)


@pytest.mark.anyio
async def test_forgot_password_returns_200_when_email_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Anti-enumeration: 200 even when email does not exist."""

    snap = await _bootstrap(tmp_path, "forgot-missing.db")
    try:
        sent: list[str] = []

        async def fake_bg(*, to_address, **kwargs):
            sent.append(to_address)

        monkeypatch.setattr(
            "flow_backend.routers.auth._send_reset_email_in_session",
            fake_bg,
        )

        async with _make_async_client() as client:
            r = await client.post(
                "/api/v1/auth/forgot-password", json={"email": "nobody@nowhere.test"}
            )
            assert r.status_code == 200
            assert r.json()["ok"] is True

        # Background task must NOT have been scheduled.
        assert sent == []
    finally:
        _restore(snap)


@pytest.mark.anyio
async def test_forgot_password_with_verified_email_creates_token_and_emails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snap = await _bootstrap(tmp_path, "forgot-ok.db")
    try:
        await _create_verified_user()

        sent: list[dict[str, Any]] = []

        async def fake_bg(**kwargs):
            sent.append(kwargs)

        monkeypatch.setattr(
            "flow_backend.routers.auth._send_reset_email_in_session",
            fake_bg,
        )

        async with _make_async_client() as client:
            r = await client.post("/api/v1/auth/forgot-password", json={"email": "PSCLY1@163.com"})
            assert r.status_code == 200

        # Token persisted.
        async with session_scope() as session:
            rows = list(await session.exec(select(PasswordResetToken)))
            assert len(rows) == 1
            assert rows[0].consumed_at is None

        assert len(sent) == 1
        assert sent[0]["to_address"] == "pscly1@163.com"
        assert sent[0]["username"] == "pscly"
        assert sent[0]["reset_url"].startswith("https://xl.test/reset-password?token=")
    finally:
        _restore(snap)


@pytest.mark.anyio
async def test_forgot_password_unverified_email_does_not_send(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snap = await _bootstrap(tmp_path, "forgot-unverified.db")
    try:
        async with session_scope() as session:
            u = User(
                username="pscly",
                password_hash=hash_password("oldpass1"),
                memos_token="tok-pscly",
                memos_id=1,
                is_active=True,
                email="pscly1@163.com",
                email_verified_at=None,  # NOT verified
            )
            session.add(u)
            await session.commit()

        sent: list[Any] = []

        async def fake_bg(**kwargs):
            sent.append(kwargs)

        monkeypatch.setattr(
            "flow_backend.routers.auth._send_reset_email_in_session",
            fake_bg,
        )

        async with _make_async_client() as client:
            r = await client.post("/api/v1/auth/forgot-password", json={"email": "pscly1@163.com"})
            assert r.status_code == 200  # Same anti-enum response

        # No email sent.
        assert sent == []
    finally:
        _restore(snap)


@pytest.mark.anyio
async def test_reset_password_full_flow_updates_password_and_invalidates_token(
    tmp_path: Path,
) -> None:
    snap = await _bootstrap(tmp_path, "reset-ok.db")
    try:
        user_id = await _create_verified_user()

        # Mint a token directly (simulating the email being received).
        async with session_scope() as session:
            user = await session.get(User, user_id)
            assert user is not None
            raw = await password_reset_service.create_reset_token(session=session, user=user)

        async with _make_async_client() as client:
            r = await client.post(
                "/api/v1/auth/reset-password",
                json={
                    "token": raw,
                    "new_password": "fresh-password-9",
                    "new_password2": "fresh-password-9",
                },
            )
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["ok"] is True

        # Password actually changed; password_changed_at set; token consumed.
        async with session_scope() as session:
            user = await session.get(User, user_id)
            assert user is not None
            assert verify_password("fresh-password-9", user.password_hash)
            assert user.password_changed_at is not None
            rows = list(await session.exec(select(PasswordResetToken)))
            assert len(rows) == 1
            assert rows[0].consumed_at is not None

        # Token is single-use: second submission fails.
        async with _make_async_client() as client:
            r2 = await client.post(
                "/api/v1/auth/reset-password",
                json={
                    "token": raw,
                    "new_password": "another9",
                    "new_password2": "another9",
                },
            )
            assert r2.status_code == 400
            assert "已失效" in r2.json().get("message", "")
    finally:
        _restore(snap)


@pytest.mark.anyio
async def test_reset_password_rejects_expired_token(tmp_path: Path) -> None:
    snap = await _bootstrap(tmp_path, "reset-expired.db")
    try:
        user_id = await _create_verified_user()

        async with session_scope() as session:
            raw = password_reset_service.generate_raw_token()
            token = PasswordResetToken(
                user_id=user_id,
                token_hash=password_reset_service._hash_token(raw),
                expires_at=utc_now() - timedelta(minutes=1),
                created_at=utc_now() - timedelta(hours=1),
            )
            session.add(token)
            await session.commit()

        async with _make_async_client() as client:
            r = await client.post(
                "/api/v1/auth/reset-password",
                json={
                    "token": raw,
                    "new_password": "fresh-pass9",
                    "new_password2": "fresh-pass9",
                },
            )
            assert r.status_code == 400
    finally:
        _restore(snap)


@pytest.mark.anyio
async def test_reset_password_rejects_mismatched_confirmation(tmp_path: Path) -> None:
    snap = await _bootstrap(tmp_path, "reset-mismatch.db")
    try:
        user_id = await _create_verified_user()
        async with session_scope() as session:
            user = await session.get(User, user_id)
            assert user is not None
            raw = await password_reset_service.create_reset_token(session=session, user=user)

        async with _make_async_client() as client:
            r = await client.post(
                "/api/v1/auth/reset-password",
                json={
                    "token": raw,
                    "new_password": "fresh-pass9",
                    "new_password2": "different9",
                },
            )
            assert r.status_code == 400
    finally:
        _restore(snap)


@pytest.mark.anyio
async def test_creating_new_token_invalidates_prior_unconsumed_tokens(
    tmp_path: Path,
) -> None:
    snap = await _bootstrap(tmp_path, "reset-invalidate.db")
    try:
        user_id = await _create_verified_user()
        async with session_scope() as session:
            user = await session.get(User, user_id)
            assert user is not None
            raw1 = await password_reset_service.create_reset_token(session=session, user=user)
            raw2 = await password_reset_service.create_reset_token(session=session, user=user)
            assert raw1 != raw2

        # raw1 should now be invalid; raw2 still valid.
        async with _make_async_client() as client:
            r1 = await client.post(
                "/api/v1/auth/reset-password",
                json={"token": raw1, "new_password": "p123456", "new_password2": "p123456"},
            )
            assert r1.status_code == 400

            r2 = await client.post(
                "/api/v1/auth/reset-password",
                json={"token": raw2, "new_password": "p123456", "new_password2": "p123456"},
            )
            assert r2.status_code == 200
    finally:
        _restore(snap)


@pytest.mark.anyio
async def test_reset_password_continues_when_memos_sync_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Memos password sync failure must NOT block the local reset.

    The DB password is the user's primary credential for this app, so we
    surface the Memos error as a warning instead of rolling back the reset.
    """

    snap = await _bootstrap(tmp_path, "reset-memos-fail.db")
    settings.dev_bypass_memos = False  # force Memos path
    old_admin_token = settings.memos_admin_token
    settings.memos_admin_token = "admin-token"
    try:
        user_id = await _create_verified_user()
        async with session_scope() as session:
            user = await session.get(User, user_id)
            assert user is not None
            raw = await password_reset_service.create_reset_token(session=session, user=user)

        class FailingMemos:
            def __init__(self, **kwargs: Any) -> None:
                pass

            async def update_user_password(self, **kwargs: Any) -> None:
                from flow_backend.memos_client import MemosClientError

                raise MemosClientError("upstream 502")

        monkeypatch.setattr("flow_backend.routers.auth.MemosClient", FailingMemos)

        async with _make_async_client() as client:
            r = await client.post(
                "/api/v1/auth/reset-password",
                json={"token": raw, "new_password": "freshpw9", "new_password2": "freshpw9"},
            )
            assert r.status_code == 200, r.text
            assert "Memos" in (r.json().get("memos_sync_warning") or "")

        async with session_scope() as session:
            user = await session.get(User, user_id)
            assert user is not None
            assert verify_password("freshpw9", user.password_hash)
    finally:
        settings.memos_admin_token = old_admin_token
        _restore(snap)
