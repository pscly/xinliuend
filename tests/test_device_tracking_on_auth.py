from __future__ import annotations

from pathlib import Path
from datetime import timedelta, timezone

import httpx
import pytest
from sqlmodel import select

from flow_backend.config import settings
from flow_backend.db import init_db, reset_engine_cache, session_scope
from flow_backend.main import app
from flow_backend.models import User, UserDevice, UserDeviceIP, utc_now
from flow_backend.security import hash_password


def _make_async_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.anyio
async def test_login_records_device_and_ip(tmp_path: Path) -> None:
    settings.database_url = f"sqlite:///{tmp_path / 'test-auth-device-login.db'}"
    reset_engine_cache()
    await init_db()

    async with session_scope() as session:
        session.add(
            User(
                username="u1",
                password_hash=hash_password("pass1234"),
                memos_id=1,
                memos_token="tok-1",
                is_active=True,
            )
        )
        await session.commit()

    old_trust = settings.trust_x_forwarded_for
    settings.trust_x_forwarded_for = True
    try:
        async with _make_async_client() as client:
            r = await client.post(
                "/api/v1/auth/login",
                json={"username": "u1", "password": "pass1234"},
                headers={
                    "X-Flow-Device-Id": "dev-001",
                    "X-Flow-Device-Name": "iPhone",
                    "X-Forwarded-For": "1.2.3.4",
                    "User-Agent": "pytest-agent",
                },
            )
            assert r.status_code == 200
    finally:
        settings.trust_x_forwarded_for = old_trust

    async with session_scope() as session:
        user = (await session.exec(select(User).where(User.username == "u1"))).first()
        assert user
        user_db_id = user.id
        assert user_db_id is not None
        user_id = int(user_db_id)
        d = (
            await session.exec(
                select(UserDevice)
                .where(UserDevice.user_id == user_id)
                .where(UserDevice.device_id == "dev-001")
            )
        ).first()
        assert d
        assert d.device_name == "iPhone"
        assert d.last_ip == "1.2.3.4"

        ip_row = (
            await session.exec(
                select(UserDeviceIP)
                .where(UserDeviceIP.user_id == user_id)
                .where(UserDeviceIP.device_id == "dev-001")
                .where(UserDeviceIP.ip == "1.2.3.4")
            )
        ).first()
        assert ip_row


@pytest.mark.anyio
async def test_register_records_device_and_ip(tmp_path: Path) -> None:
    settings.database_url = f"sqlite:///{tmp_path / 'test-auth-device-register.db'}"
    reset_engine_cache()
    await init_db()

    old_trust = settings.trust_x_forwarded_for
    old_bypass = settings.dev_bypass_memos
    settings.trust_x_forwarded_for = True
    settings.dev_bypass_memos = True
    try:
        async with _make_async_client() as client:
            r = await client.post(
                "/api/v1/auth/register",
                json={"username": "u2", "password": "pass1234"},
                headers={
                    "X-Flow-Device-Id": "dev-002",
                    "X-Flow-Device-Name": "Android",
                    "X-Forwarded-For": "5.6.7.8",
                    "User-Agent": "pytest-agent",
                },
            )
            assert r.status_code == 200
    finally:
        settings.trust_x_forwarded_for = old_trust
        settings.dev_bypass_memos = old_bypass

    async with session_scope() as session:
        user = (await session.exec(select(User).where(User.username == "u2"))).first()
        assert user
        user_db_id = user.id
        assert user_db_id is not None
        user_id = int(user_db_id)
        d = (
            await session.exec(
                select(UserDevice)
                .where(UserDevice.user_id == user_id)
                .where(UserDevice.device_id == "dev-002")
            )
        ).first()
        assert d
        assert d.device_name == "Android"
        assert d.last_ip == "5.6.7.8"


@pytest.mark.anyio
async def test_readonly_auth_request_updates_device_last_seen(tmp_path: Path) -> None:
    settings.database_url = f"sqlite:///{tmp_path / 'test-auth-device-readonly.db'}"
    reset_engine_cache()
    await init_db()

    old_time = utc_now() - timedelta(days=1)
    async with session_scope() as session:
        user = User(
            username="u3",
            password_hash=hash_password("pass1234"),
            memos_id=3,
            memos_token="tok-3",
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        assert user.id is not None
        session.add(
            UserDevice(
                user_id=int(user.id),
                device_id="dev-003",
                device_name="Pixel",
                first_seen=old_time,
                last_seen=old_time,
                created_at=old_time,
                updated_at=old_time,
            )
        )
        await session.commit()

    old_async = settings.device_tracking_async
    settings.device_tracking_async = False
    try:
        async with _make_async_client() as client:
            r = await client.get(
                "/api/v1/todo/lists",
                headers={
                    "Authorization": "Bearer tok-3",
                    "X-Flow-Device-Id": "dev-003",
                    "X-Flow-Device-Name": "Pixel",
                },
            )
            assert r.status_code == 200
    finally:
        settings.device_tracking_async = old_async

    async with session_scope() as session:
        user = (await session.exec(select(User).where(User.username == "u3"))).first()
        assert user
        user_db_id = user.id
        assert user_db_id is not None
        d = (
            await session.exec(
                select(UserDevice)
                .where(UserDevice.user_id == int(user_db_id))
                .where(UserDevice.device_id == "dev-003")
            )
        ).first()
        assert d
        last_seen = d.last_seen
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        assert last_seen.timestamp() > old_time.timestamp()
