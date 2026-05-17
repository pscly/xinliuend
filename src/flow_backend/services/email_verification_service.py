"""Email verification used for the "bind email to account" flow.

A 6-digit numeric code is sent to the proposed email; the user submits it
back within the TTL to confirm ownership and we then store the (lowercased,
trimmed) email on the user row.

Codes are stored as SHA-256 hex hashes so the DB never contains the raw code.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import Final

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.config import settings
from flow_backend.models import EmailVerificationToken, User, as_utc, utc_now
from flow_backend.services.email_service import EmailSendError, render_email, send_email


PURPOSE_BIND: Final[str] = "bind"


def normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _generate_code() -> str:
    # 6-digit zero-padded numeric code.
    return f"{secrets.randbelow(10**6):06d}"


async def _ensure_email_not_used_by_other(
    session: AsyncSession, *, email: str, user_id: int
) -> None:
    row = (
        await session.exec(
            select(User).where((User.email == email) & (User.id != int(user_id)))
        )
    ).first()
    if row is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该邮箱已被其它账号绑定",
        )


async def request_email_verification(
    *,
    session: AsyncSession,
    user: User,
    email: str,
    ip: str | None = None,
) -> None:
    """Generate a fresh code, persist its hash and email a 6-digit code to the user."""

    user_id = user.id
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user id missing",
        )

    normalized = normalize_email(email)
    if not normalized or "@" not in normalized or len(normalized) > 320:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请填写合法的邮箱地址",
        )

    await _ensure_email_not_used_by_other(session, email=normalized, user_id=int(user_id))

    code = _generate_code()
    ttl = int(settings.email_verification_code_ttl_seconds)
    expires_at = utc_now() + timedelta(seconds=ttl)

    token = EmailVerificationToken(
        user_id=int(user_id),
        email=normalized,
        code_hash=_hash_code(code),
        purpose=PURPOSE_BIND,
        expires_at=expires_at,
        ip=ip,
    )
    session.add(token)
    await session.commit()

    html, text = render_email(
        "email_verify",
        {
            "brand_name": "心流（Flow）",
            "username": user.username,
            "email": normalized,
            "code": code,
            "ttl_minutes": max(1, ttl // 60),
        },
    )
    try:
        await send_email(
            session=session,
            to_address=normalized,
            subject="【心流 Flow】邮箱绑定验证码",
            html=html,
            text=text,
        )
    except EmailSendError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"邮件发送失败：{exc}",
        ) from exc


async def confirm_email_verification(
    *,
    session: AsyncSession,
    user: User,
    email: str,
    code: str,
) -> None:
    """Validate the submitted code and atomically bind the email to the user."""

    user_id = user.id
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user id missing",
        )

    normalized = normalize_email(email)
    code = (code or "").strip()
    if not normalized or not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邮箱与验证码均为必填",
        )

    await _ensure_email_not_used_by_other(session, email=normalized, user_id=int(user_id))

    code_hash = _hash_code(code)
    now = utc_now()
    row = (
        await session.exec(
            select(EmailVerificationToken).where(
                (EmailVerificationToken.user_id == int(user_id))
                & (EmailVerificationToken.email == normalized)
                & (EmailVerificationToken.code_hash == code_hash)
                & (EmailVerificationToken.consumed_at.is_(None))  # type: ignore[union-attr]
                & (EmailVerificationToken.purpose == PURPOSE_BIND)
            )
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码错误或与邮箱不匹配",
        )
    expires_at = as_utc(row.expires_at)
    if expires_at is not None and expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码已过期，请重新获取",
        )

    user_row = await session.get(User, int(user_id))
    if user_row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token"
        )

    user_row.email = normalized
    user_row.email_verified_at = now
    session.add(user_row)

    row.consumed_at = now
    session.add(row)

    await session.commit()
