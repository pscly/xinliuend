"""Resolve SMTP configuration for sending mail.

Resolution order:
1. DB-stored runtime config (`site_settings` keys with `smtp.` prefix). Admin
   edits live here so they take effect without restart.
2. Environment-variable fallback declared on `Settings` (`EMAIL_HOST`, etc.).
   Useful for first-time bootstrap or test environments.

Stored passwords are encrypted with the existing Fernet key so the DB never
holds the SMTP credential in plain text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.config import settings
from flow_backend.password_crypto import decrypt_password, encrypt_password
from flow_backend.services import site_settings_service


SMTP_KEY_PREFIX = "smtp."
SMTP_KEYS = (
    "smtp.host",
    "smtp.port",
    "smtp.username",
    "smtp.password",  # stored as Fernet-encrypted string
    "smtp.from_address",
    "smtp.from_name",
    "smtp.use_ssl",  # implicit TLS (port 465)
    "smtp.use_starttls",  # STARTTLS (port 587)
    "smtp.reply_to",
)


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    username: str
    password: str
    from_address: str
    from_name: str = ""
    use_ssl: bool = True
    use_starttls: bool = False
    reply_to: str = ""

    def is_complete(self) -> bool:
        return bool(
            self.host and self.port and self.username and self.password and self.from_address
        )


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _coerce_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return default


def _coerce_str(value: Any, default: str = "") -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return default
    return str(value).strip()


def encrypt_smtp_password(plain: str) -> str:
    plain = (plain or "").strip()
    if not plain:
        return ""
    return encrypt_password(plain)


def decrypt_smtp_password(stored: str) -> str:
    stored = (stored or "").strip()
    if not stored:
        return ""
    return decrypt_password(stored)


async def load_smtp_config(session: AsyncSession) -> SmtpConfig:
    """Build the effective SMTP config from DB overrides + env fallback."""

    db_values = await site_settings_service.get_settings_by_prefix(session, SMTP_KEY_PREFIX)

    def pick_str(key: str, env_value: str) -> str:
        raw = db_values.get(f"{SMTP_KEY_PREFIX}{key}")
        out = _coerce_str(raw, "")
        return out if out else env_value

    def pick_int(key: str, env_value: int) -> int:
        if f"{SMTP_KEY_PREFIX}{key}" in db_values:
            return _coerce_int(db_values[f"{SMTP_KEY_PREFIX}{key}"], env_value)
        return env_value

    def pick_bool(key: str, env_value: bool) -> bool:
        if f"{SMTP_KEY_PREFIX}{key}" in db_values:
            return _coerce_bool(db_values[f"{SMTP_KEY_PREFIX}{key}"], env_value)
        return env_value

    host = pick_str("host", settings.email_host)
    port = pick_int("port", settings.email_port)
    username = pick_str("username", settings.email_username)

    raw_pwd = db_values.get(f"{SMTP_KEY_PREFIX}password")
    if isinstance(raw_pwd, str) and raw_pwd.strip():
        try:
            password = decrypt_smtp_password(raw_pwd)
        except ValueError:
            password = ""
    else:
        password = (settings.email_password or "").strip()

    from_address = pick_str("from_address", settings.email_from_address)
    from_name = pick_str("from_name", settings.email_from_name)
    use_ssl = pick_bool("use_ssl", settings.email_use_ssl)
    use_starttls = pick_bool("use_starttls", settings.email_use_starttls)
    reply_to = pick_str("reply_to", "")

    return SmtpConfig(
        host=host,
        port=port,
        username=username,
        password=password,
        from_address=from_address,
        from_name=from_name,
        use_ssl=use_ssl,
        use_starttls=use_starttls,
        reply_to=reply_to,
    )


async def save_smtp_config(
    session: AsyncSession,
    *,
    host: str,
    port: int,
    username: str,
    password: str | None,  # None = keep existing (don't overwrite)
    from_address: str,
    from_name: str = "",
    use_ssl: bool = True,
    use_starttls: bool = False,
    reply_to: str = "",
    updated_by: str | None = None,
) -> None:
    """Persist admin-supplied SMTP config to site_settings.

    `password=None` means "keep the existing stored password" (so admins editing
    the form don't have to retype the SMTP credential each time). An empty
    string explicitly clears it.
    """

    items: dict[str, Any] = {
        f"{SMTP_KEY_PREFIX}host": _coerce_str(host),
        f"{SMTP_KEY_PREFIX}port": int(port),
        f"{SMTP_KEY_PREFIX}username": _coerce_str(username),
        f"{SMTP_KEY_PREFIX}from_address": _coerce_str(from_address),
        f"{SMTP_KEY_PREFIX}from_name": _coerce_str(from_name),
        f"{SMTP_KEY_PREFIX}use_ssl": bool(use_ssl),
        f"{SMTP_KEY_PREFIX}use_starttls": bool(use_starttls),
        f"{SMTP_KEY_PREFIX}reply_to": _coerce_str(reply_to),
    }
    if password is not None:
        items[f"{SMTP_KEY_PREFIX}password"] = encrypt_smtp_password(password)
    await site_settings_service.set_many(session, items, updated_by=updated_by)


async def has_stored_password(session: AsyncSession) -> bool:
    raw = await site_settings_service.get_setting(session, f"{SMTP_KEY_PREFIX}password")
    return isinstance(raw, str) and bool(raw.strip())
