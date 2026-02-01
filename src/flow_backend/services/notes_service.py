from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.models import utc_now
from flow_backend.models_notes import Note, NoteRevision
from flow_backend.repositories import note_revisions_repo, notes_repo
from flow_backend.services.notes_tags_service import set_note_tags
from flow_backend.sync_utils import clamp_client_updated_at_ms, now_ms


def _derive_title_from_body(body_md: str) -> str:
    for line in (body_md or "").splitlines():
        line = line.strip()
        if line:
            return line[:500]
    return ""


def _server_snapshot(*, note: Note, tags: list[str]) -> dict[str, Any]:
    return {
        "id": note.id,
        "title": note.title,
        "body_md": note.body_md,
        "tags": tags,
        "client_updated_at_ms": note.client_updated_at_ms,
        "created_at": note.created_at,
        "updated_at": note.updated_at,
        "deleted_at": note.deleted_at,
    }


async def create_note(
    *,
    session: AsyncSession,
    user_id: int,
    id_: str | None,
    title: str | None,
    body_md: str,
    tags: list[str],
    client_updated_at_ms: int | None,
) -> tuple[Note, list[str]]:
    note_id = id_ or str(uuid.uuid4())
    incoming_ms = clamp_client_updated_at_ms(client_updated_at_ms) or now_ms()

    final_title = (title or "").strip() or _derive_title_from_body(body_md)

    note = Note(
        id=note_id,
        user_id=user_id,
        title=final_title,
        body_md=body_md,
        client_updated_at_ms=incoming_ms,
        updated_at=utc_now(),
    )

    try:
        if session.in_transaction():
            session.add(note)
            await session.flush()
            tags_out = await set_note_tags(session, user_id=user_id, note_id=note_id, tags=tags)
            await session.commit()
            return note, tags_out

        async with session.begin():
            session.add(note)
            await session.flush()
            tags_out = await set_note_tags(session, user_id=user_id, note_id=note_id, tags=tags)
            return note, tags_out
    except Exception:
        try:
            await session.rollback()
        except Exception:
            pass
        raise


async def get_note(
    *,
    session: AsyncSession,
    user_id: int,
    note_id: str,
    include_deleted: bool,
) -> tuple[Note, list[str]]:
    note = await notes_repo.get_note(
        session, user_id=user_id, note_id=note_id, include_deleted=include_deleted
    )
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="note not found")
    tags = await note_revisions_repo.list_note_tags(session, user_id=user_id, note_id=note_id)
    return note, tags


async def patch_note(
    *,
    session: AsyncSession,
    user_id: int,
    note_id: str,
    title: str | None,
    body_md: str | None,
    tags: list[str] | None,
    client_updated_at_ms: int,
) -> tuple[Note, list[str]]:
    incoming_ms = clamp_client_updated_at_ms(client_updated_at_ms) or now_ms()

    try:
        if session.in_transaction():
            note = await notes_repo.get_note_active(session, user_id=user_id, note_id=note_id)
            if note is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="note not found")

            current_tags = await note_revisions_repo.list_note_tags(
                session, user_id=user_id, note_id=note_id
            )
            if incoming_ms < note.client_updated_at_ms:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "message": "conflict",
                        "details": {
                            "server_snapshot": _server_snapshot(note=note, tags=current_tags)
                        },
                    },
                )

            # Store revision snapshot of the previous state.
            session.add(
                NoteRevision(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    note_id=note_id,
                    kind="NORMAL",
                    reason="update",
                    snapshot_json={
                        "title": note.title,
                        "body_md": note.body_md,
                        "tags": current_tags,
                        "client_updated_at_ms": note.client_updated_at_ms,
                    },
                    client_updated_at_ms=incoming_ms,
                    updated_at=utc_now(),
                    created_at=utc_now(),
                )
            )

            if title is not None:
                note.title = title.strip()
            if body_md is not None:
                note.body_md = body_md
                if (title is None) and not note.title.strip():
                    note.title = _derive_title_from_body(note.body_md)
            note.client_updated_at_ms = incoming_ms
            note.updated_at = utc_now()
            session.add(note)

            if tags is not None:
                tags_out = await set_note_tags(session, user_id=user_id, note_id=note_id, tags=tags)
            else:
                tags_out = current_tags

            await session.commit()
            return note, tags_out

        async with session.begin():
            note = await notes_repo.get_note_active(session, user_id=user_id, note_id=note_id)
            if note is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="note not found")

            current_tags = await note_revisions_repo.list_note_tags(
                session, user_id=user_id, note_id=note_id
            )
            if incoming_ms < note.client_updated_at_ms:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "message": "conflict",
                        "details": {
                            "server_snapshot": _server_snapshot(note=note, tags=current_tags)
                        },
                    },
                )

            session.add(
                NoteRevision(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    note_id=note_id,
                    kind="NORMAL",
                    reason="update",
                    snapshot_json={
                        "title": note.title,
                        "body_md": note.body_md,
                        "tags": current_tags,
                        "client_updated_at_ms": note.client_updated_at_ms,
                    },
                    client_updated_at_ms=incoming_ms,
                    updated_at=utc_now(),
                    created_at=utc_now(),
                )
            )

            if title is not None:
                note.title = title.strip()
            if body_md is not None:
                note.body_md = body_md
                if (title is None) and not note.title.strip():
                    note.title = _derive_title_from_body(note.body_md)
            note.client_updated_at_ms = incoming_ms
            note.updated_at = utc_now()
            session.add(note)

            if tags is not None:
                tags_out = await set_note_tags(session, user_id=user_id, note_id=note_id, tags=tags)
            else:
                tags_out = current_tags

            return note, tags_out
    except Exception:
        try:
            await session.rollback()
        except Exception:
            pass
        raise


async def delete_note(
    *,
    session: AsyncSession,
    user_id: int,
    note_id: str,
    client_updated_at_ms: int,
) -> None:
    incoming_ms = clamp_client_updated_at_ms(client_updated_at_ms) or now_ms()

    note = await notes_repo.get_note(
        session, user_id=user_id, note_id=note_id, include_deleted=True
    )
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="note not found")

    current_tags = await note_revisions_repo.list_note_tags(
        session, user_id=user_id, note_id=note_id
    )
    if incoming_ms < note.client_updated_at_ms:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "conflict",
                "details": {"server_snapshot": _server_snapshot(note=note, tags=current_tags)},
            },
        )

    if note.deleted_at is None:
        session.add(
            NoteRevision(
                id=str(uuid.uuid4()),
                user_id=user_id,
                note_id=note_id,
                kind="NORMAL",
                reason="delete",
                snapshot_json={
                    "title": note.title,
                    "body_md": note.body_md,
                    "tags": current_tags,
                    "client_updated_at_ms": note.client_updated_at_ms,
                },
                client_updated_at_ms=incoming_ms,
                updated_at=utc_now(),
                created_at=utc_now(),
            )
        )

    note.deleted_at = utc_now()
    note.client_updated_at_ms = incoming_ms
    note.updated_at = utc_now()
    session.add(note)
    await session.commit()


async def restore_note(
    *,
    session: AsyncSession,
    user_id: int,
    note_id: str,
    client_updated_at_ms: int,
) -> tuple[Note, list[str]]:
    incoming_ms = clamp_client_updated_at_ms(client_updated_at_ms) or now_ms()

    note = await notes_repo.get_note(
        session, user_id=user_id, note_id=note_id, include_deleted=True
    )
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="note not found")

    current_tags = await note_revisions_repo.list_note_tags(
        session, user_id=user_id, note_id=note_id
    )
    if incoming_ms < note.client_updated_at_ms:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "conflict",
                "details": {"server_snapshot": _server_snapshot(note=note, tags=current_tags)},
            },
        )

    # Snapshot pre-restore state.
    session.add(
        NoteRevision(
            id=str(uuid.uuid4()),
            user_id=user_id,
            note_id=note_id,
            kind="NORMAL",
            reason="restore",
            snapshot_json={
                "title": note.title,
                "body_md": note.body_md,
                "tags": current_tags,
                "client_updated_at_ms": note.client_updated_at_ms,
            },
            client_updated_at_ms=incoming_ms,
            updated_at=utc_now(),
            created_at=utc_now(),
        )
    )

    note.deleted_at = None
    note.client_updated_at_ms = incoming_ms
    note.updated_at = utc_now()
    session.add(note)
    await session.commit()
    return note, current_tags
