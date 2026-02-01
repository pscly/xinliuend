from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import timedelta
from datetime import timezone

from fastapi import HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.config import settings
from flow_backend.models import utc_now
from flow_backend.models_notes import Attachment, Note, NoteShare
from flow_backend.repositories import notes_search_repo, shares_repo
from flow_backend.sync_utils import now_ms


_DEFAULT_EXPIRES_SECONDS = 60 * 60 * 24 * 7
_MAX_EXPIRES_SECONDS = 60 * 60 * 24 * 30
_TOKEN_PREFIX_LEN = 8


def _compute_token_hmac_hex(*, token: str) -> str:
    secret = settings.share_token_secret.strip()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="share token secret not configured",
        )
    digest = hmac.new(secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest


def _build_share_url(*, token: str) -> str:
    base = settings.public_base_url.rstrip("/")
    return f"{base}/api/v2/public/shares/{token}"


def _assume_utc(dt):
    # SQLite may return naive datetimes even when the column was declared with timezone=True.
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def create_share(
    *,
    session: AsyncSession,
    user_id: int,
    note_id: str,
    expires_in_seconds: int | None,
) -> tuple[str, str, str]:
    expires = expires_in_seconds or _DEFAULT_EXPIRES_SECONDS
    if expires > _MAX_EXPIRES_SECONDS:
        # Defensive; schema already enforces this.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="expires_in_seconds too large",
        )

    token = secrets.token_urlsafe(32)
    token_prefix = token[:_TOKEN_PREFIX_LEN]
    token_hmac_hex = _compute_token_hmac_hex(token=token)
    created_ms = now_ms()

    share = NoteShare(
        id=str(uuid.uuid4()),
        user_id=user_id,
        note_id=note_id,
        token_prefix=token_prefix,
        token_hmac_hex=token_hmac_hex,
        expires_at=utc_now() + timedelta(seconds=expires),
        revoked_at=None,
        client_updated_at_ms=created_ms,
    )

    try:
        if session.in_transaction():
            note = await shares_repo.get_note_active(session, user_id=user_id, note_id=note_id)
            if note is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="note not found")
            session.add(share)
            await session.commit()
        else:
            async with session.begin():
                note = await shares_repo.get_note_active(session, user_id=user_id, note_id=note_id)
                if note is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="note not found",
                    )
                session.add(share)
    except Exception:
        try:
            await session.rollback()
        except Exception:
            pass
        raise

    share_url = _build_share_url(token=token)
    return share.id, token, share_url


async def revoke_share(*, session: AsyncSession, user_id: int, share_id: str) -> None:
    share = await shares_repo.get_share_by_id(session, user_id=user_id, share_id=share_id)
    if share is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="share not found")

    if share.revoked_at is not None:
        return

    share.revoked_at = utc_now()
    share.updated_at = utc_now()
    share.client_updated_at_ms = now_ms()
    session.add(share)
    await session.commit()


async def _resolve_share_by_token(*, session: AsyncSession, share_token: str) -> NoteShare:
    token = (share_token or "").strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="share not found")

    token_prefix = token[:_TOKEN_PREFIX_LEN]
    token_hmac_hex = _compute_token_hmac_hex(token=token)

    share = await shares_repo.get_share_by_token(
        session,
        token_prefix=token_prefix,
        token_hmac_hex=token_hmac_hex,
    )
    if share is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="share not found")

    # Constant-time verify (pinned) even though we already filtered in SQL.
    if not hmac.compare_digest(share.token_hmac_hex, token_hmac_hex):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="share not found")

    if share.revoked_at is not None:
        # Do not reveal revoked share existence.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="share not found")

    expires_at = _assume_utc(share.expires_at)
    if expires_at is not None and expires_at <= utc_now():
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="share expired")

    return share


async def get_shared_note(
    *,
    session: AsyncSession,
    share_token: str,
) -> tuple[Note, list[str], list[Attachment]]:
    share = await _resolve_share_by_token(session=session, share_token=share_token)

    note = await shares_repo.get_note_active(session, user_id=share.user_id, note_id=share.note_id)
    if note is None:
        # Do not reveal note existence.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")

    tags_by_note = await notes_search_repo.get_tags_for_notes(
        session, user_id=share.user_id, note_ids=[note.id]
    )
    tags = tags_by_note.get(note.id, [])

    attachments = await shares_repo.list_attachments_for_note(
        session, user_id=share.user_id, note_id=note.id
    )
    return note, tags, attachments


async def get_shared_attachment(
    *,
    session: AsyncSession,
    share_token: str,
    attachment_id: str,
) -> tuple[Attachment, int, str]:
    share = await _resolve_share_by_token(session=session, share_token=share_token)

    note = await shares_repo.get_note_active(session, user_id=share.user_id, note_id=share.note_id)
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")

    attachment = await shares_repo.get_attachment_for_note(
        session,
        user_id=share.user_id,
        note_id=note.id,
        attachment_id=attachment_id,
    )
    if attachment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")

    return attachment, share.user_id, note.id
