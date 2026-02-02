"""Notes router (v2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.db import get_session
from flow_backend.deps import get_current_user
from flow_backend.models import User
from flow_backend.services import notes_search_service, notes_service
from flow_backend.v2.schemas import Note as NoteSchema
from flow_backend.v2.schemas import (
    NoteCreateRequest,
    NoteList,
    NotePatchRequest,
    NoteRestoreRequest,
)

router = APIRouter(tags=["notes"])


@router.post("/notes", response_model=NoteSchema, status_code=status.HTTP_201_CREATED)
async def create_note(
    payload: NoteCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> NoteSchema:
    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user missing id",
        )

    note, tags = await notes_service.create_note(
        session=session,
        user_id=int(user.id),
        id_=payload.id,
        title=payload.title,
        body_md=payload.body_md,
        tags=payload.tags,
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


@router.get("/notes", response_model=NoteList)
async def list_notes(
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
    tag: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    include_deleted: Annotated[bool, Query()] = False,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> NoteList:
    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user missing id",
        )

    notes, tags_by_note_id, total = await notes_search_service.list_notes(
        session=session,
        user_id=int(user.id),
        limit=limit,
        offset=offset,
        tag=tag,
        q=q,
        include_deleted=include_deleted,
    )

    items = [
        NoteSchema(
            id=n.id,
            title=n.title,
            body_md=n.body_md,
            tags=tags_by_note_id.get(n.id, []),
            client_updated_at_ms=n.client_updated_at_ms,
            created_at=n.created_at,
            updated_at=n.updated_at,
            deleted_at=n.deleted_at,
        )
        for n in notes
    ]
    return NoteList(items=items, total=total, limit=limit, offset=offset)


@router.get("/notes/{note_id}", response_model=NoteSchema)
async def get_note(
    note_id: str,
    include_deleted: Annotated[bool, Query()] = False,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> NoteSchema:
    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user missing id",
        )

    note, tags = await notes_service.get_note(
        session=session,
        user_id=int(user.id),
        note_id=note_id,
        include_deleted=include_deleted,
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


@router.patch("/notes/{note_id}", response_model=NoteSchema)
async def patch_note(
    note_id: str,
    payload: NotePatchRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> NoteSchema:
    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user missing id",
        )

    note, tags = await notes_service.patch_note(
        session=session,
        user_id=int(user.id),
        note_id=note_id,
        title=payload.title,
        body_md=payload.body_md,
        tags=payload.tags,
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


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: str,
    client_updated_at_ms: Annotated[int, Query(ge=0)],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user missing id",
        )

    await notes_service.delete_note(
        session=session,
        user_id=int(user.id),
        note_id=note_id,
        client_updated_at_ms=client_updated_at_ms,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/notes/{note_id}/restore", response_model=NoteSchema)
async def restore_note(
    note_id: str,
    payload: NoteRestoreRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> NoteSchema:
    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user missing id",
        )

    note, tags = await notes_service.restore_note(
        session=session,
        user_id=int(user.id),
        note_id=note_id,
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
