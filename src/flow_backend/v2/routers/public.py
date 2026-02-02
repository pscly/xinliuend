"""Public (anonymous) routes for share links (v2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, Response
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.db import get_session
from flow_backend.integrations.storage.local_storage import LocalObjectStorage
from flow_backend.integrations.storage.object_storage import ObjectStorage, get_object_storage
from flow_backend.http_headers import build_content_disposition_attachment, sanitize_filename
from flow_backend.services import shares_service
from flow_backend.v2.schemas.notes import Note as NoteSchema
from flow_backend.v2.schemas.shares import SharedAttachment, SharedNote

router = APIRouter(tags=["public"])


@router.get("/public/shares/{share_token}", response_model=SharedNote)
async def get_shared_note(
    share_token: str,
    session: AsyncSession = Depends(get_session),
) -> SharedNote:
    note, tags, attachments = await shares_service.get_shared_note(
        session=session, share_token=share_token
    )

    note_schema = NoteSchema(
        id=note.id,
        title=note.title,
        body_md=note.body_md,
        tags=tags,
        client_updated_at_ms=note.client_updated_at_ms,
        created_at=note.created_at,
        updated_at=note.updated_at,
        deleted_at=note.deleted_at,
    )
    return SharedNote(
        note=note_schema,
        attachments=[
            SharedAttachment(
                id=a.id,
                filename=a.filename,
                content_type=a.content_type,
                size_bytes=a.size_bytes,
            )
            for a in attachments
        ],
    )


@router.get("/public/shares/{share_token}/attachments/{attachment_id}")
async def download_shared_attachment(
    share_token: str,
    attachment_id: str,
    session: AsyncSession = Depends(get_session),
    storage: ObjectStorage = Depends(get_object_storage),
) -> Response:
    attachment, _user_id, _note_id = await shares_service.get_shared_attachment(
        session=session,
        share_token=share_token,
        attachment_id=attachment_id,
    )

    media_type = attachment.content_type or "application/octet-stream"
    filename = sanitize_filename(attachment.filename or attachment.id)
    if isinstance(storage, LocalObjectStorage):
        path = storage.resolve_path(attachment.storage_key)
        if not path.exists():
            # Mirror private download behavior.
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
        return FileResponse(path, media_type=media_type, filename=filename)

    data = await storage.get_bytes(attachment.storage_key)
    headers = {"Content-Disposition": build_content_disposition_attachment(filename)}
    return Response(content=data, media_type=media_type, headers=headers)
