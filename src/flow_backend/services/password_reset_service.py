"""Stateless password-reset token issue/consume helpers.

We generate a urlsafe random token (32 bytes -> 43 chars) and only persist
its SHA-256 hash plus expiry/consumed state. The raw token is sent in the
reset email and never stored.

Email enumeration protection lives at the route layer (HTTP response is the
same whether or not the email is registered/verified).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.config import settings
from flow_backend.models import PasswordResetToken, User, as_utc, utc_now


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_raw_token() -> str:
    return secrets.token_urlsafe(32)


async def create_reset_token(
    *,
    session: AsyncSession,
    user: User,
    requester_ip: str | None = None,
    requester_ua: str | None = None,
) -> str:
    """Create a new reset token; invalidates all the user's previous unconsumed tokens.

    Returns the raw token (caller emails it; never store it).
    """

    if user.id is None:
        raise RuntimeError("user id missing")

    now = utc_now()
    # Invalidate any previous unconsumed tokens so a user clicking the latest
    # email link is the only valid path forward.
    prev_rows = list(
        await session.exec(
            select(PasswordResetToken).where(
                (PasswordResetToken.user_id == int(user.id))
                & (PasswordResetToken.consumed_at.is_(None))  # type: ignore[union-attr]
            )
        )
    )
    for prev in prev_rows:
        prev.consumed_at = now
        session.add(prev)

    raw = generate_raw_token()
    ttl = int(settings.password_reset_token_ttl_seconds)
    token = PasswordResetToken(
        user_id=int(user.id),
        token_hash=_hash_token(raw),
        expires_at=now + timedelta(seconds=ttl),
        created_at=now,
        requester_ip=requester_ip,
        requester_ua=requester_ua,
    )
    session.add(token)
    await session.commit()
    return raw


async def consume_reset_token(
    *,
    session: AsyncSession,
    raw_token: str,
) -> User | None:
    """Resolve+consume a token. Returns the User if valid, None otherwise.

    Caller is responsible for updating the password and password_changed_at.
    """

    if not raw_token or not isinstance(raw_token, str):
        return None
    token_hash = _hash_token(raw_token.strip())
    if not token_hash:
        return None

    row = (
        await session.exec(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
        )
    ).first()
    if row is None:
        return None
    if row.consumed_at is not None:
        return None
    now = utc_now()
    expires_at = as_utc(row.expires_at)
    if expires_at is not None and expires_at < now:
        return None

    user = await session.get(User, int(row.user_id))
    if user is None or not user.is_active:
        return None

    row.consumed_at = now
    session.add(row)
    await session.commit()
    return user
