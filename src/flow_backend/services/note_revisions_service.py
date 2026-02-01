from __future__ import annotations

import uuid
from typing import Any, cast

from fastapi import HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.models import utc_now
from flow_backend.models_notes import Note, NoteRevision
from flow_backend.repositories import note_revisions_repo
from flow_backend.services.notes_tags_service import set_note_tags
from flow_backend.sync_utils import clamp_client_updated_at_ms


def _snapshot_from_note(*, note: Note, tags: list[str]) -> dict[str, Any]:
    return {
        "title": note.title,
        "body_md": note.body_md,
        "tags": tags,
        "client_updated_at_ms": note.client_updated_at_ms,
    }


async def list_revisions(
    *,
    session: AsyncSession,
    user_id: int,
    note_id: str,
    limit: int = 100,
) -> list[NoteRevision]:
    note = await note_revisions_repo.get_note_active(session, user_id=user_id, note_id=note_id)
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="note not found")
    return await note_revisions_repo.list_revisions(
        session, user_id=user_id, note_id=note_id, limit=limit
    )


async def restore_revision(
    *,
    session: AsyncSession,
    user_id: int,
    note_id: str,
    revision_id: str,
    client_updated_at_ms: int,
) -> tuple[Note, list[str]]:
    incoming_ms = clamp_client_updated_at_ms(client_updated_at_ms)
    if incoming_ms <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid client_updated_at_ms"
        )

    try:
        if session.in_transaction():
            note = await note_revisions_repo.get_note_active(
                session, user_id=user_id, note_id=note_id
            )
            if note is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="note not found")
            if incoming_ms < note.client_updated_at_ms:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="conflict")

            rev = await note_revisions_repo.get_revision(
                session, user_id=user_id, note_id=note_id, revision_id=revision_id
            )
            if rev is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="revision not found"
                )

            current_tags = await note_revisions_repo.list_note_tags(
                session, user_id=user_id, note_id=note_id
            )
            session.add(
                NoteRevision(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    note_id=note_id,
                    kind="NORMAL",
                    reason="restore",
                    snapshot_json=_snapshot_from_note(note=note, tags=current_tags),
                    client_updated_at_ms=incoming_ms,
                    updated_at=utc_now(),
                    created_at=utc_now(),
                )
            )

            snap = cast(dict[str, Any], rev.snapshot_json or {})
            note.title = str(snap.get("title") or "")
            note.body_md = str(snap.get("body_md") or "")
            note.client_updated_at_ms = incoming_ms
            note.updated_at = utc_now()
            session.add(note)

            tags = list(snap.get("tags") or [])
            tags_out = await set_note_tags(session, user_id=user_id, note_id=note_id, tags=tags)
            await session.commit()
            return note, tags_out

        async with session.begin():
            note = await note_revisions_repo.get_note_active(
                session, user_id=user_id, note_id=note_id
            )
            if note is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="note not found")
            if incoming_ms < note.client_updated_at_ms:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="conflict")

            rev = await note_revisions_repo.get_revision(
                session, user_id=user_id, note_id=note_id, revision_id=revision_id
            )
            if rev is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="revision not found"
                )

            current_tags = await note_revisions_repo.list_note_tags(
                session, user_id=user_id, note_id=note_id
            )
            session.add(
                NoteRevision(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    note_id=note_id,
                    kind="NORMAL",
                    reason="restore",
                    snapshot_json=_snapshot_from_note(note=note, tags=current_tags),
                    client_updated_at_ms=incoming_ms,
                    updated_at=utc_now(),
                    created_at=utc_now(),
                )
            )

            snap = cast(dict[str, Any], rev.snapshot_json or {})
            note.title = str(snap.get("title") or "")
            note.body_md = str(snap.get("body_md") or "")
            note.client_updated_at_ms = incoming_ms
            note.updated_at = utc_now()
            session.add(note)

            tags = list(snap.get("tags") or [])
            tags_out = await set_note_tags(session, user_id=user_id, note_id=note_id, tags=tags)
            return note, tags_out
    except Exception:
        try:
            await session.rollback()
        except Exception:
            pass
        raise
