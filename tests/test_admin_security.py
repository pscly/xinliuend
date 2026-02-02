from __future__ import annotations

import httpx
import pytest

from flow_backend.config import settings
from flow_backend.main import app


def _make_async_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.anyio
async def test_admin_login_blocks_open_redirect_next_url():
    settings.admin_basic_user = "admin"
    settings.admin_basic_password = "pw"
    settings.admin_session_secret = "test-secret"

    async with _make_async_client() as client:
        r = await client.post(
            "/admin/login",
            data={"username": "admin", "password": "pw", "next": "//evil.example.com"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/admin"


@pytest.mark.anyio
async def test_admin_login_blocks_absolute_url_next_url():
    settings.admin_basic_user = "admin"
    settings.admin_basic_password = "pw"
    settings.admin_session_secret = "test-secret"

    async with _make_async_client() as client:
        r = await client.post(
            "/admin/login",
            data={"username": "admin", "password": "pw", "next": "https://evil.example.com"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/admin"


@pytest.mark.anyio
async def test_admin_login_sets_secure_cookie_from_forwarded_proto():
    old_user = settings.admin_basic_user
    old_pass = settings.admin_basic_password
    old_secret = settings.admin_session_secret
    old_trust_proto = settings.trust_x_forwarded_proto
    try:
        settings.admin_basic_user = "admin"
        settings.admin_basic_password = "pw"
        settings.admin_session_secret = "test-secret"
        settings.trust_x_forwarded_proto = True

        async with _make_async_client() as client:
            r = await client.post(
                "/admin/login",
                headers={"X-Forwarded-Proto": "https"},
                data={"username": "admin", "password": "pw", "next": "/admin"},
                follow_redirects=False,
            )
            assert r.status_code == 303
            set_cookie = r.headers.get("set-cookie") or ""
            assert "Secure" in set_cookie
    finally:
        settings.admin_basic_user = old_user
        settings.admin_basic_password = old_pass
        settings.admin_session_secret = old_secret
        settings.trust_x_forwarded_proto = old_trust_proto
