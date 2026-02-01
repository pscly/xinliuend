from __future__ import annotations

import hashlib
import uuid

from fastapi import HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.integrations.storage.object_storage import (
    ObjectStorage,
    build_attachment_storage_key,
)
from flow_backend.models_notes import Attachment, NoteAttachment
from flow_backend.repositories import attachments_repo
from flow_backend.sync_utils import now_ms


async def create_note_attachment(
    *,
    session: AsyncSession,
    storage: ObjectStorage,
    user_id: int,
    note_id: str,
    filename: str | None,
    content_type: str | None,
    data: bytes,
) -> Attachment:
    attachment_id = str(uuid.uuid4())
    storage_key = build_attachment_storage_key(user_id=user_id, attachment_id=attachment_id)

    created_ms = now_ms()
    sha256_hex = hashlib.sha256(data).hexdigest()

    attachment = Attachment(
        id=attachment_id,
        user_id=user_id,
        storage_key=storage_key,
        filename=filename or None,
        content_type=content_type or None,
        size_bytes=len(data),
        sha256_hex=sha256_hex,
        client_updated_at_ms=created_ms,
    )

    link = NoteAttachment(
        id=str(uuid.uuid4()),
        user_id=user_id,
        note_id=note_id,
        attachment_id=attachment_id,
        client_updated_at_ms=created_ms,
    )

    # Best-effort consistency: if DB commit fails, delete the stored object.
    try:
        # FastAPI dependencies (like auth) may have already triggered an implicit
        # transaction on the request-scoped session. In that case, `session.begin()`
        # would raise, so we fall back to an explicit commit/rollback boundary.
        if session.in_transaction():
            note = await attachments_repo.get_note_active(session, user_id=user_id, note_id=note_id)
            if note is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="note not found",
                )

            session.add(attachment)
            session.add(link)
            await session.flush()
            await storage.put_bytes(storage_key, data, content_type=content_type)
            await session.commit()
        else:
            async with session.begin():
                note = await attachments_repo.get_note_active(
                    session, user_id=user_id, note_id=note_id
                )
                if note is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="note not found",
                    )

                session.add(attachment)
                session.add(link)
                await session.flush()
                await storage.put_bytes(storage_key, data, content_type=content_type)
    except Exception:
        try:
            await session.rollback()
        except Exception:
            pass
        try:
            await storage.delete(storage_key)
        except Exception:
            # Best-effort cleanup.
            pass
        raise

    return attachment
