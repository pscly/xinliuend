"""Async email sender backed by aiosmtplib.

Reads SMTP configuration via `smtp_config.load_smtp_config` so admins can
edit SMTP settings at runtime without restarting the service.

Templates live in `src/flow_backend/templates/emails/<name>.html` and
`<name>.txt`. `render_email` returns both — callers pass the result to
`send_email`. Plain-text bodies improve deliverability with strict mail
gateways (163, gmail) so all transactional emails ship both parts.
"""

from __future__ import annotations

import logging
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from typing import Any

import aiosmtplib
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.services.smtp_config import SmtpConfig, load_smtp_config


logger = logging.getLogger(__name__)


class EmailSendError(RuntimeError):
    pass


_TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates" / "emails"


def _build_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
        keep_trailing_newline=True,
    )


_jinja_env = _build_jinja_env()


def render_email(template_name: str, ctx: dict[str, Any]) -> tuple[str, str]:
    """Render `<template>.html` and `<template>.txt` with the same context.

    Returns (html, text). If the .txt variant is missing, falls back to a
    naive plain-text derivation from the HTML (strip tags). Most templates
    should ship both variants so the plain-text body reads well.
    """

    html_tpl = _jinja_env.get_template(f"{template_name}.html")
    html = html_tpl.render(**ctx)
    try:
        text_tpl = _jinja_env.get_template(f"{template_name}.txt")
        text = text_tpl.render(**ctx)
    except Exception:
        # Best-effort plain-text from HTML: strip tags.
        import re as _re

        text = _re.sub(r"<[^>]+>", "", html)
    return html, text


def _format_from(cfg: SmtpConfig) -> str:
    if cfg.from_name:
        return formataddr((cfg.from_name, cfg.from_address))
    return cfg.from_address


def _safe_repr_config(cfg: SmtpConfig) -> str:
    return (
        f"SmtpConfig(host={cfg.host!r}, port={cfg.port}, username={cfg.username!r}, "
        f"from={cfg.from_address!r}, use_ssl={cfg.use_ssl}, use_starttls={cfg.use_starttls}, "
        f"password=***)"
    )


async def send_email(
    *,
    session: AsyncSession,
    to_address: str,
    subject: str,
    html: str,
    text: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> None:
    """Send a single transactional email.

    Raises EmailSendError when SMTP is unconfigured or aiosmtplib errors.
    """

    cfg = await load_smtp_config(session)
    if not cfg.is_complete():
        raise EmailSendError(
            "SMTP not configured. Set SMTP_HOST/SMTP_USERNAME/SMTP_PASSWORD/"
            "SMTP_FROM_ADDRESS via the admin panel (/admin/smtp) or .env."
        )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = _format_from(cfg)
    msg["To"] = to_address
    if cfg.reply_to:
        msg["Reply-To"] = cfg.reply_to
    if extra_headers:
        for k, v in extra_headers.items():
            msg[k] = v

    if text is None:
        text = ""
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    try:
        await aiosmtplib.send(
            msg,
            hostname=cfg.host,
            port=cfg.port,
            username=cfg.username,
            password=cfg.password,
            use_tls=bool(cfg.use_ssl),
            start_tls=bool(cfg.use_starttls and not cfg.use_ssl),
            timeout=30.0,
        )
    except Exception as exc:
        logger.warning(
            "email send failed to=%s via %s: %s",
            to_address,
            _safe_repr_config(cfg),
            exc,
        )
        raise EmailSendError(f"send failed: {exc}") from exc

    logger.info("email sent to=%s subject=%s via %s", to_address, subject, cfg.host)
