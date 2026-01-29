from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlmodel import select

from flow_backend.config import settings
from flow_backend.db import init_db, reset_engine_cache, session_scope
from flow_backend.main import app
from flow_backend.models import User, UserDevice, UserDeviceIP
from flow_backend.security import hash_password


def _make_async_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.anyio
async def test_device_tracking_and_admin_page(tmp_path: Path) -> None:
    settings.database_url = f"sqlite:///{tmp_path / 'test-admin-user-devices.db'}"
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

    # Force deterministic IP capture via X-Forwarded-For.
    old_trust = settings.trust_x_forwarded_for
    settings.trust_x_forwarded_for = True
    try:
        async with _make_async_client() as client:
            r = await client.get(
                "/api/v1/settings",
                headers={
                    "Authorization": "Bearer tok-1",
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
        user_id = int(user.id)
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
        assert (d.last_user_agent or "").startswith("pytest-agent")

        ip_row = (
            await session.exec(
                select(UserDeviceIP)
                .where(UserDeviceIP.user_id == user_id)
                .where(UserDeviceIP.device_id == "dev-001")
                .where(UserDeviceIP.ip == "1.2.3.4")
            )
        ).first()
        assert ip_row

    # Admin can view devices page.
    settings.admin_basic_user = "admin"
    settings.admin_basic_password = "pw"
    settings.admin_session_secret = "test-secret"

    async with _make_async_client() as client:
        login = await client.post(
            "/admin/login",
            data={"username": "admin", "password": "pw", "next": "/admin"},
            follow_redirects=False,
        )
        assert login.status_code == 303
        # httpx client keeps cookies; we can call the page directly.
        page = await client.get(f"/admin/users/{user_id}/devices")
        assert page.status_code == 200
        assert "dev-001" in page.text
