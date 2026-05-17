from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path
from typing import Any

import pytest

from flow_backend.config import settings
from flow_backend.db import init_db, reset_engine_cache, session_scope
from flow_backend.services import email_service, site_settings_service
from flow_backend.services.email_service import EmailSendError, render_email, send_email
from flow_backend.services.smtp_config import save_smtp_config


async def _bootstrap(tmp_path: Path, db_name: str) -> str:
    old_db = settings.database_url
    settings.database_url = f"sqlite:///{tmp_path / db_name}"
    reset_engine_cache()
    site_settings_service.invalidate_cache()
    await init_db()
    return old_db


def _restore(old_db: str) -> None:
    settings.database_url = old_db
    site_settings_service.invalidate_cache()


def test_render_password_reset_template_uses_html_and_text_variants() -> None:
    html, text = render_email(
        "password_reset",
        {
            "brand_name": "心流（Flow）",
            "username": "pscly",
            "reset_url": "https://xl.pscly.cc/reset-password?token=xyz",
            "ttl_minutes": 30,
        },
    )
    assert "心流" in html
    assert "pscly" in html
    assert "reset-password?token=xyz" in html
    # Plain text variant
    assert "心流" in text
    assert "pscly" in text
    assert "reset-password?token=xyz" in text
    # Plain text MUST NOT contain HTML tags (delivers better, prevents leak).
    assert "<a " not in text
    assert "<html" not in text.lower()


def test_render_email_verify_template_includes_code() -> None:
    html, text = render_email(
        "email_verify",
        {
            "brand_name": "心流（Flow）",
            "username": "pscly",
            "email": "pscly1@163.com",
            "code": "493021",
            "ttl_minutes": 10,
        },
    )
    assert "493021" in html
    assert "493021" in text
    assert "pscly1@163.com" in html


@pytest.mark.anyio
async def test_send_email_raises_when_smtp_not_configured(tmp_path: Path) -> None:
    old_db = await _bootstrap(tmp_path, "no-smtp.db")
    old_host = settings.email_host
    old_user = settings.email_username
    old_pwd = settings.email_password
    old_from = settings.email_from_address
    try:
        # Clear env fallback too.
        settings.email_host = ""
        settings.email_username = ""
        settings.email_password = ""
        settings.email_from_address = ""

        async with session_scope() as session:
            with pytest.raises(EmailSendError, match="SMTP not configured"):
                await send_email(
                    session=session,
                    to_address="x@example.com",
                    subject="hello",
                    html="<p>hi</p>",
                )
    finally:
        settings.email_host = old_host
        settings.email_username = old_user
        settings.email_password = old_pwd
        settings.email_from_address = old_from
        _restore(old_db)


@pytest.mark.anyio
async def test_send_email_uses_aiosmtplib_with_db_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old_db = await _bootstrap(tmp_path, "smtp-ok.db")
    old_key = settings.user_password_encryption_key
    settings.user_password_encryption_key = "WmfpBBPjCEIb_IJvZP_t6aG9AZ51qHm_iNg0Q_y6Bno="
    try:
        async with session_scope() as session:
            await save_smtp_config(
                session,
                host="smtp.163.com",
                port=465,
                username="pscly1@163.com",
                password="UXQSTCRIEKULJEDL",
                from_address="pscly1@163.com",
                from_name="心流",
                use_ssl=True,
                use_starttls=False,
            )

        captured: dict[str, Any] = {}

        async def fake_send(message: EmailMessage, **kwargs: Any) -> Any:
            captured["message"] = message
            captured["kwargs"] = kwargs
            return None

        monkeypatch.setattr(email_service.aiosmtplib, "send", fake_send)

        async with session_scope() as session:
            await send_email(
                session=session,
                to_address="dest@example.com",
                subject="hello",
                html="<p>hi</p>",
                text="hi",
            )

        kwargs = captured["kwargs"]
        assert kwargs["hostname"] == "smtp.163.com"
        assert kwargs["port"] == 465
        assert kwargs["username"] == "pscly1@163.com"
        assert kwargs["password"] == "UXQSTCRIEKULJEDL"
        assert kwargs["use_tls"] is True
        assert kwargs["start_tls"] is False

        msg = captured["message"]
        assert msg["To"] == "dest@example.com"
        assert msg["Subject"] == "hello"
        # From should include the friendly name in <local> form.
        assert "pscly1@163.com" in msg["From"]
        assert "心流" in msg["From"]
    finally:
        settings.user_password_encryption_key = old_key
        _restore(old_db)


@pytest.mark.anyio
async def test_send_email_translates_aiosmtplib_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A network error must surface as EmailSendError (not raw aiosmtplib exception)."""

    old_db = await _bootstrap(tmp_path, "smtp-fail.db")
    old_key = settings.user_password_encryption_key
    settings.user_password_encryption_key = "WmfpBBPjCEIb_IJvZP_t6aG9AZ51qHm_iNg0Q_y6Bno="
    try:
        async with session_scope() as session:
            await save_smtp_config(
                session,
                host="smtp.bad.example.com",
                port=465,
                username="user@example.com",
                password="pwd",
                from_address="user@example.com",
            )

        async def boom(*args: Any, **kwargs: Any) -> None:
            raise OSError("connection refused")

        monkeypatch.setattr(email_service.aiosmtplib, "send", boom)

        async with session_scope() as session:
            with pytest.raises(EmailSendError, match="send failed"):
                await send_email(
                    session=session,
                    to_address="dest@example.com",
                    subject="x",
                    html="<p>x</p>",
                )
    finally:
        settings.user_password_encryption_key = old_key
        _restore(old_db)
