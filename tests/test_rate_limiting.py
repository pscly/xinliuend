from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote

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


@pytest.mark.anyio
async def test_auth_login_rate_limited_returns_429(tmp_path: Path):
    old_db = settings.database_url
    old_trust = settings.trust_x_forwarded_for
    old_window = settings.rate_limit_window_seconds
    old_ip_limit = settings.auth_login_rate_limit_per_ip
    old_ip_user_limit = settings.auth_login_rate_limit_per_ip_user
    try:
        settings.database_url = f"sqlite:///{tmp_path / 'test-rate-limit.db'}"
        settings.trust_x_forwarded_for = True
        settings.rate_limit_window_seconds = 60
        settings.auth_login_rate_limit_per_ip = 2
        settings.auth_login_rate_limit_per_ip_user = 2

        reset_engine_cache()
        await init_db()

        async with session_scope() as session:
            session.add(
                User(
                    username="u1",
                    password_hash=hash_password("pass1234"),
                    memos_id=1,
                    memos_token="tok-u1",
                    is_active=True,
                )
            )
            await session.commit()

        async with _make_async_client() as client:
            headers = {"X-Forwarded-For": "1.2.3.4"}
            for _ in range(2):
                r = await client.post(
                    "/api/v1/auth/login",
                    headers=headers,
                    json={"username": "u1", "password": "wrong"},
                )
                assert r.status_code in (401, 429)
            r_last = await client.post(
                "/api/v1/auth/login",
                headers=headers,
                json={"username": "u1", "password": "wrong"},
            )
            assert r_last.status_code == 429
            assert r_last.headers.get("retry-after")
    finally:
        settings.database_url = old_db
        settings.trust_x_forwarded_for = old_trust
        settings.rate_limit_window_seconds = old_window
        settings.auth_login_rate_limit_per_ip = old_ip_limit
        settings.auth_login_rate_limit_per_ip_user = old_ip_user_limit


@pytest.mark.anyio
async def test_admin_login_rate_limited_redirects(tmp_path: Path):
    old_db = settings.database_url
    old_trust = settings.trust_x_forwarded_for
    old_window = settings.rate_limit_window_seconds
    old_admin_limit = settings.admin_login_rate_limit_per_ip
    old_user = settings.admin_basic_user
    old_pass = settings.admin_basic_password
    old_secret = settings.admin_session_secret
    try:
        settings.database_url = f"sqlite:///{tmp_path / 'test-admin-rate-limit.db'}"
        settings.trust_x_forwarded_for = True
        settings.rate_limit_window_seconds = 60
        settings.admin_login_rate_limit_per_ip = 2
        settings.admin_basic_user = "admin"
        settings.admin_basic_password = "pw"
        settings.admin_session_secret = "test-secret"

        reset_engine_cache()
        await init_db()

        async with _make_async_client() as client:
            headers = {"X-Forwarded-For": "9.9.9.9"}
            for _ in range(2):
                r = await client.post(
                    "/admin/login",
                    headers=headers,
                    data={"username": "admin", "password": "wrong", "next": "/admin"},
                    follow_redirects=False,
                )
                assert r.status_code == 303

            r3 = await client.post(
                "/admin/login",
                headers=headers,
                data={"username": "admin", "password": "wrong", "next": "/admin"},
                follow_redirects=False,
            )
            assert r3.status_code == 303
            loc = unquote(r3.headers.get("location") or "")
            assert "请求过于频繁" in loc
    finally:
        settings.database_url = old_db
        settings.trust_x_forwarded_for = old_trust
        settings.rate_limit_window_seconds = old_window
        settings.admin_login_rate_limit_per_ip = old_admin_limit
        settings.admin_basic_user = old_user
        settings.admin_basic_password = old_pass
        settings.admin_session_secret = old_secret
