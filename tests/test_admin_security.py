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
