from __future__ import annotations

from pathlib import Path

import pytest

from flow_backend.config import settings
from flow_backend.db import init_db, reset_engine_cache, session_scope
from flow_backend.services import site_settings_service
from flow_backend.services.smtp_config import (
    encrypt_smtp_password,
    decrypt_smtp_password,
    has_stored_password,
    load_smtp_config,
    save_smtp_config,
)


async def _bootstrap(tmp_path: Path, db_name: str = "site-settings.db") -> str:
    old_db = settings.database_url
    settings.database_url = f"sqlite:///{tmp_path / db_name}"
    reset_engine_cache()
    site_settings_service.invalidate_cache()
    await init_db()
    return old_db


def _restore(old_db: str) -> None:
    settings.database_url = old_db
    site_settings_service.invalidate_cache()


@pytest.mark.anyio
async def test_site_settings_crud_and_cache(tmp_path: Path) -> None:
    old_db = await _bootstrap(tmp_path, "crud.db")
    try:
        async with session_scope() as session:
            assert await site_settings_service.get_setting(session, "smtp.host") is None

            await site_settings_service.set_setting(
                session, "smtp.host", "smtp.example.com", updated_by="admin"
            )
            assert await site_settings_service.get_setting(session, "smtp.host") == "smtp.example.com"

            # Prefix queries return only matching keys.
            await site_settings_service.set_setting(session, "smtp.port", 465)
            await site_settings_service.set_setting(session, "other.flag", True)
            kv = await site_settings_service.get_settings_by_prefix(session, "smtp.")
            assert kv == {"smtp.host": "smtp.example.com", "smtp.port": 465}

            # Update + cache invalidation.
            await site_settings_service.set_setting(session, "smtp.host", "smtp.changed.com")
            assert await site_settings_service.get_setting(session, "smtp.host") == "smtp.changed.com"
    finally:
        _restore(old_db)


@pytest.mark.anyio
async def test_smtp_password_is_encrypted_at_rest_and_decrypts(tmp_path: Path) -> None:
    """Stored smtp password must never be in plain text."""

    old_db = await _bootstrap(tmp_path, "smtp-pwd.db")
    old_key = settings.user_password_encryption_key
    settings.user_password_encryption_key = "WmfpBBPjCEIb_IJvZP_t6aG9AZ51qHm_iNg0Q_y6Bno="
    try:
        async with session_scope() as session:
            await save_smtp_config(
                session,
                host="smtp.163.com",
                port=465,
                username="pscly1@163.com",
                password="UXQSTCRIEKULJEDL",  # 163 authorization code
                from_address="pscly1@163.com",
                from_name="心流",
                use_ssl=True,
                use_starttls=False,
            )

        async with session_scope() as session:
            raw = await site_settings_service.get_setting(session, "smtp.password")
            assert isinstance(raw, str)
            assert raw != "UXQSTCRIEKULJEDL"
            # Decryption must round-trip.
            assert decrypt_smtp_password(raw) == "UXQSTCRIEKULJEDL"

            cfg = await load_smtp_config(session)
            assert cfg.host == "smtp.163.com"
            assert cfg.port == 465
            assert cfg.username == "pscly1@163.com"
            assert cfg.password == "UXQSTCRIEKULJEDL"
            assert cfg.from_address == "pscly1@163.com"
            assert cfg.is_complete() is True
            assert await has_stored_password(session) is True
    finally:
        settings.user_password_encryption_key = old_key
        _restore(old_db)


@pytest.mark.anyio
async def test_save_smtp_with_none_password_preserves_existing(tmp_path: Path) -> None:
    old_db = await _bootstrap(tmp_path, "preserve.db")
    old_key = settings.user_password_encryption_key
    settings.user_password_encryption_key = "WmfpBBPjCEIb_IJvZP_t6aG9AZ51qHm_iNg0Q_y6Bno="
    try:
        async with session_scope() as session:
            await save_smtp_config(
                session,
                host="smtp.163.com",
                port=465,
                username="user@163.com",
                password="initial-secret",
                from_address="user@163.com",
            )

        async with session_scope() as session:
            # Now update other fields but pass password=None.
            await save_smtp_config(
                session,
                host="smtp.163.com",
                port=465,
                username="user@163.com",
                password=None,  # preserve
                from_address="newuser@163.com",
            )
            cfg = await load_smtp_config(session)
            assert cfg.password == "initial-secret"
            assert cfg.from_address == "newuser@163.com"
    finally:
        settings.user_password_encryption_key = old_key
        _restore(old_db)


@pytest.mark.anyio
async def test_load_smtp_falls_back_to_env_when_db_empty(tmp_path: Path) -> None:
    old_db = await _bootstrap(tmp_path, "env-fallback.db")
    old_email_host = settings.email_host
    old_email_port = settings.email_port
    old_email_username = settings.email_username
    old_email_password = settings.email_password
    old_email_from = settings.email_from_address
    try:
        settings.email_host = "smtp.env.example.com"
        settings.email_port = 587
        settings.email_username = "env-user@example.com"
        settings.email_password = "env-secret"
        settings.email_from_address = "env-user@example.com"

        async with session_scope() as session:
            cfg = await load_smtp_config(session)
            assert cfg.host == "smtp.env.example.com"
            assert cfg.port == 587
            assert cfg.username == "env-user@example.com"
            assert cfg.password == "env-secret"
            assert cfg.is_complete() is True
    finally:
        settings.email_host = old_email_host
        settings.email_port = old_email_port
        settings.email_username = old_email_username
        settings.email_password = old_email_password
        settings.email_from_address = old_email_from
        _restore(old_db)


@pytest.mark.anyio
async def test_encrypt_decrypt_helpers_handle_empty() -> None:
    assert encrypt_smtp_password("") == ""
    assert encrypt_smtp_password("   ") == ""
    assert decrypt_smtp_password("") == ""
    assert decrypt_smtp_password("   ") == ""
