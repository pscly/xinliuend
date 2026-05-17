from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path
from typing import Any

import httpx
import pytest

from flow_backend.config import settings
from flow_backend.db import init_db, reset_engine_cache, session_scope
from flow_backend.main import app
from flow_backend.services import email_service, site_settings_service
from flow_backend.services.smtp_config import load_smtp_config


def _make_async_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _bootstrap(tmp_path: Path, db_name: str) -> dict[str, Any]:
    snap = {
        "database_url": settings.database_url,
        "admin_basic_user": settings.admin_basic_user,
        "admin_basic_password": settings.admin_basic_password,
        "admin_session_secret": settings.admin_session_secret,
        "user_password_encryption_key": settings.user_password_encryption_key,
    }
    settings.database_url = f"sqlite:///{tmp_path / db_name}"
    settings.admin_basic_user = "admin"
    settings.admin_basic_password = "pw"
    settings.admin_session_secret = "secret"
    settings.user_password_encryption_key = "WmfpBBPjCEIb_IJvZP_t6aG9AZ51qHm_iNg0Q_y6Bno="
    reset_engine_cache()
    site_settings_service.invalidate_cache()
    await init_db()
    return snap


def _restore(snap: dict[str, Any]) -> None:
    for k, v in snap.items():
        setattr(settings, k, v)
    site_settings_service.invalidate_cache()


async def _login_admin(client: httpx.AsyncClient) -> str:
    r = await client.post(
        "/admin/login",
        data={"username": "admin", "password": "pw", "next": "/admin/smtp"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    page = await client.get("/admin/smtp")
    assert page.status_code == 200
    marker = 'name="csrf_token" value="'
    html = page.text
    start = html.index(marker) + len(marker)
    end = html.index('"', start)
    return html[start:end]


@pytest.mark.anyio
async def test_admin_smtp_get_unauthenticated_redirects_to_login(tmp_path: Path) -> None:
    snap = await _bootstrap(tmp_path, "smtp-auth.db")
    try:
        async with _make_async_client() as client:
            r = await client.get("/admin/smtp", follow_redirects=False)
            assert r.status_code == 303
            assert "/admin/login" in r.headers["location"]
    finally:
        _restore(snap)


@pytest.mark.anyio
async def test_admin_smtp_save_and_persisted(tmp_path: Path) -> None:
    snap = await _bootstrap(tmp_path, "smtp-save.db")
    try:
        async with _make_async_client() as client:
            csrf = await _login_admin(client)
            r = await client.post(
                "/admin/smtp",
                data={
                    "csrf_token": csrf,
                    "host": "smtp.163.com",
                    "port": "465",
                    "username": "pscly1@163.com",
                    "password": "UXQSTCRIEKULJEDL",
                    "from_address": "pscly1@163.com",
                    "from_name": "心流",
                    "use_ssl": "1",
                    "use_starttls": "",
                    "reply_to": "",
                },
                follow_redirects=False,
            )
            assert r.status_code == 303
            assert "msg=" in r.headers["location"]

        async with session_scope() as session:
            cfg = await load_smtp_config(session)
            assert cfg.host == "smtp.163.com"
            assert cfg.port == 465
            assert cfg.username == "pscly1@163.com"
            assert cfg.password == "UXQSTCRIEKULJEDL"
            assert cfg.use_ssl is True
            assert cfg.from_address == "pscly1@163.com"
    finally:
        _restore(snap)


@pytest.mark.anyio
async def test_admin_smtp_save_with_empty_password_preserves_existing(tmp_path: Path) -> None:
    snap = await _bootstrap(tmp_path, "smtp-keep.db")
    try:
        async with _make_async_client() as client:
            csrf = await _login_admin(client)
            # First save with a password.
            r = await client.post(
                "/admin/smtp",
                data={
                    "csrf_token": csrf,
                    "host": "smtp.163.com",
                    "port": "465",
                    "username": "u@163.com",
                    "password": "initial-secret",
                    "from_address": "u@163.com",
                    "use_ssl": "1",
                },
                follow_redirects=False,
            )
            assert r.status_code == 303

            # Re-save with blank password — must keep the existing one.
            csrf2 = await _login_admin(client)
            r2 = await client.post(
                "/admin/smtp",
                data={
                    "csrf_token": csrf2,
                    "host": "smtp.163.com",
                    "port": "587",  # change port
                    "username": "u@163.com",
                    "password": "",  # blank => keep
                    "from_address": "u@163.com",
                    "use_starttls": "1",
                    "use_ssl": "",
                },
                follow_redirects=False,
            )
            assert r2.status_code == 303

        async with session_scope() as session:
            cfg = await load_smtp_config(session)
            assert cfg.port == 587
            assert cfg.use_starttls is True
            assert cfg.password == "initial-secret"  # unchanged
    finally:
        _restore(snap)


@pytest.mark.anyio
async def test_admin_smtp_test_button_triggers_send_email(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snap = await _bootstrap(tmp_path, "smtp-test.db")
    try:
        captured: dict[str, Any] = {}

        async def fake_send(message: EmailMessage, **kwargs: Any) -> Any:
            captured["message"] = message
            captured["kwargs"] = kwargs

        monkeypatch.setattr(email_service.aiosmtplib, "send", fake_send)

        async with _make_async_client() as client:
            csrf = await _login_admin(client)
            # Save config first.
            await client.post(
                "/admin/smtp",
                data={
                    "csrf_token": csrf,
                    "host": "smtp.163.com",
                    "port": "465",
                    "username": "u@163.com",
                    "password": "secret",
                    "from_address": "u@163.com",
                    "use_ssl": "1",
                },
                follow_redirects=False,
            )

            csrf2 = await _login_admin(client)
            r = await client.post(
                "/admin/smtp/test",
                data={"csrf_token": csrf2, "to_address": "dest@163.com"},
            )
            assert r.status_code == 200
            assert r.json() == {"ok": True}

        assert captured["message"]["To"] == "dest@163.com"
        assert "SMTP 测试邮件" in captured["message"]["Subject"]
        assert captured["kwargs"]["hostname"] == "smtp.163.com"
    finally:
        _restore(snap)


@pytest.mark.anyio
async def test_admin_smtp_test_without_config_returns_error(
    tmp_path: Path,
) -> None:
    snap = await _bootstrap(tmp_path, "smtp-no-config.db")
    old_host = settings.email_host
    settings.email_host = ""
    settings.email_username = ""
    settings.email_password = ""
    settings.email_from_address = ""
    try:
        async with _make_async_client() as client:
            csrf = await _login_admin(client)
            r = await client.post(
                "/admin/smtp/test",
                data={"csrf_token": csrf, "to_address": "dest@example.com"},
            )
            assert r.status_code == 400
            assert r.json().get("ok") is False
    finally:
        settings.email_host = old_host
        _restore(snap)
