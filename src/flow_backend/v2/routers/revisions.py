"""Note revisions (v2)."""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.db import get_session
from flow_backend.deps import get_current_user
from flow_backend.models import User
from flow_backend.services import note_revisions_service
from flow_backend.v2.schemas.notes import Note as NoteSchema
from flow_backend.v2.schemas.revisions import (
    NoteRevision as NoteRevisionSchema,
    NoteRevisionList,
    NoteRevisionRestoreRequest,
    NoteSnapshot,
)

router = APIRouter(tags=["revisions"])


@router.get("/notes/{note_id}/revisions", response_model=NoteRevisionList)
async def list_revisions(
    note_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> NoteRevisionList:
    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user missing id",
        )

    rows = await note_revisions_service.list_revisions(
        session=session,
        user_id=int(user.id),
        note_id=note_id,
        limit=limit,
    )

    items: list[NoteRevisionSchema] = []
    for r in rows:
        snap = cast(dict[str, Any], r.snapshot_json or {})
        items.append(
            NoteRevisionSchema(
                id=r.id,
                note_id=r.note_id,
                kind=r.kind,
                reason=r.reason,
                created_at=r.created_at,
                snapshot=NoteSnapshot(
                    title=str(snap.get("title") or ""),
                    body_md=str(snap.get("body_md") or ""),
                    tags=list(snap.get("tags") or []),
                    client_updated_at_ms=int(snap.get("client_updated_at_ms") or 0),
                ),
            )
        )
    return NoteRevisionList(items=items)


@router.post(
    "/notes/{note_id}/revisions/{revision_id}/restore",
    response_model=NoteSchema,
)
async def restore_revision(
    note_id: str,
    revision_id: str,
    payload: NoteRevisionRestoreRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> NoteSchema:
    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user missing id",
        )

    note, tags = await note_revisions_service.restore_revision(
        session=session,
        user_id=int(user.id),
        note_id=note_id,
        revision_id=revision_id,
        client_updated_at_ms=payload.client_updated_at_ms,
    )

    return NoteSchema(
        id=note.id,
        title=note.title,
        body_md=note.body_md,
        tags=tags,
        client_updated_at_ms=note.client_updated_at_ms,
        created_at=note.created_at,
        updated_at=note.updated_at,
        deleted_at=note.deleted_at,
    )
