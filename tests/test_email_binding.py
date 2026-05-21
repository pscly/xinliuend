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
from flow_backend.models import EmailVerificationToken, User, utc_now
from flow_backend.security import hash_password
from flow_backend.services import email_verification_service, site_settings_service


def _make_async_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _bootstrap(tmp_path: Path, db_name: str) -> dict[str, Any]:
    snap = {
        "database_url": settings.database_url,
        "user_password_encryption_key": settings.user_password_encryption_key,
        "email_host": settings.email_host,
        "email_username": settings.email_username,
        "email_password": settings.email_password,
        "email_from_address": settings.email_from_address,
    }
    settings.database_url = f"sqlite:///{tmp_path / db_name}"
    settings.user_password_encryption_key = "WmfpBBPjCEIb_IJvZP_t6aG9AZ51qHm_iNg0Q_y6Bno="
    settings.email_host = "smtp.test"
    settings.email_username = "user@test"
    settings.email_password = "pwd"
    settings.email_from_address = "user@test"
    reset_engine_cache()
    site_settings_service.invalidate_cache()
    await init_db()
    return snap


def _restore(snap: dict[str, Any]) -> None:
    for k, v in snap.items():
        setattr(settings, k, v)
    site_settings_service.invalidate_cache()


async def _create_user(username: str = "pscly", token: str = "tok-1") -> int:
    async with session_scope() as session:
        u = User(
            username=username,
            password_hash=hash_password("pw123456"),
            memos_token=token,
            memos_id=1,
            is_active=True,
        )
        session.add(u)
        await session.commit()
        await session.refresh(u)
        assert u.id is not None
        return int(u.id)


@pytest.mark.anyio
async def test_request_and_confirm_email_binding_full_flow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snap = await _bootstrap(tmp_path, "bind.db")
    try:
        await _create_user("pscly", token="bearer-1")

        captured_codes: list[str] = []

        async def fake_send_email(*, session, to_address, subject, html, text=None, **kwargs):
            # Extract code from the rendered template for the test.
            import re

            m = re.search(r"\b(\d{6})\b", text or "")
            if m:
                captured_codes.append(m.group(1))

        monkeypatch.setattr(
            "flow_backend.services.email_verification_service.send_email",
            fake_send_email,
        )

        async with _make_async_client() as client:
            client.headers["Authorization"] = "Bearer bearer-1"

            r = await client.post("/api/v1/me/email/request", json={"email": "PSCLY1@163.com"})
            assert r.status_code == 200, r.text
            assert captured_codes, "send_email must have been called"

            # Database stored the email in lowercase form.
            async with session_scope() as session:
                rows = list(await session.exec(select(EmailVerificationToken)))
                assert len(rows) == 1
                assert rows[0].email == "pscly1@163.com"

            code = captured_codes[0]
            r = await client.post(
                "/api/v1/me/email/confirm",
                json={"email": "pscly1@163.com", "code": code},
            )
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["email"] == "pscly1@163.com"
            assert data["email_verified"] is True

            # /me reflects the new binding.
            r2 = await client.get("/api/v1/me")
            assert r2.json()["email"] == "pscly1@163.com"
            assert r2.json()["email_verified"] is True
    finally:
        _restore(snap)


@pytest.mark.anyio
async def test_confirm_with_wrong_code_returns_400(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snap = await _bootstrap(tmp_path, "wrong-code.db")
    try:
        await _create_user("pscly", token="bearer-2")

        async def fake_send_email(**kwargs):
            return None

        monkeypatch.setattr(
            "flow_backend.services.email_verification_service.send_email",
            fake_send_email,
        )

        async with _make_async_client() as client:
            client.headers["Authorization"] = "Bearer bearer-2"
            await client.post("/api/v1/me/email/request", json={"email": "a@b.com"})
            r = await client.post(
                "/api/v1/me/email/confirm",
                json={"email": "a@b.com", "code": "000000"},
            )
            assert r.status_code == 400
    finally:
        _restore(snap)


@pytest.mark.anyio
async def test_email_already_used_by_other_returns_409(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snap = await _bootstrap(tmp_path, "dup-email.db")
    try:
        # bob already has the email bound.
        async with session_scope() as session:
            bob = User(
                username="bob",
                password_hash=hash_password("pw123456"),
                memos_token="bob-tok",
                memos_id=99,
                is_active=True,
                email="shared@example.com",
                email_verified_at=utc_now(),
            )
            session.add(bob)
            await session.commit()

        await _create_user("alice", token="alice-tok")

        async def fake_send_email(**kwargs):
            return None

        monkeypatch.setattr(
            "flow_backend.services.email_verification_service.send_email",
            fake_send_email,
        )

        async with _make_async_client() as client:
            client.headers["Authorization"] = "Bearer alice-tok"
            r = await client.post("/api/v1/me/email/request", json={"email": "shared@example.com"})
            assert r.status_code == 409
    finally:
        _restore(snap)


@pytest.mark.anyio
async def test_expired_code_returns_400(tmp_path: Path) -> None:
    snap = await _bootstrap(tmp_path, "expired.db")
    try:
        user_id = await _create_user("pscly", token="bearer-3")

        # Plant an expired token directly.
        async with session_scope() as session:
            code = "123456"
            token = EmailVerificationToken(
                user_id=user_id,
                email="x@y.com",
                code_hash=email_verification_service._hash_code(code),
                purpose=email_verification_service.PURPOSE_BIND,
                expires_at=utc_now() - timedelta(minutes=1),
            )
            session.add(token)
            await session.commit()

        async with _make_async_client() as client:
            client.headers["Authorization"] = "Bearer bearer-3"
            r = await client.post(
                "/api/v1/me/email/confirm",
                json={"email": "x@y.com", "code": "123456"},
            )
            assert r.status_code == 400
            assert "过期" in r.json().get("message", "")
    finally:
        _restore(snap)
