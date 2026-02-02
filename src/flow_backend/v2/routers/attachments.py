"""Attachments router (v2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.db import get_session
from flow_backend.deps import get_current_user
from flow_backend.integrations.storage.local_storage import LocalObjectStorage
from flow_backend.integrations.storage.object_storage import ObjectStorage, get_object_storage
from flow_backend.models import User
from flow_backend.repositories import attachments_repo
from flow_backend.services import attachments_service
from flow_backend.config import settings
from flow_backend.v2.schemas.attachments import Attachment as AttachmentSchema

router = APIRouter()


async def _read_upload_file_limited(*, file: UploadFile, max_bytes: int) -> bytes:
    # Read the file in chunks and hard-stop once size exceeds max_bytes.
    buf = bytearray()
    chunk_size = 1024 * 1024
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="attachment too large",
            )
    return bytes(buf)


@router.post(
    "/notes/{note_id}/attachments",
    response_model=AttachmentSchema,
    status_code=status.HTTP_201_CREATED,
)
async def upload_note_attachment(
    note_id: str,
    file: Annotated[UploadFile, File()],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    storage: ObjectStorage = Depends(get_object_storage),
) -> AttachmentSchema:
    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user missing id",
        )

    max_bytes = int(settings.attachments_max_size_bytes)
    if max_bytes > 0:
        data = await _read_upload_file_limited(file=file, max_bytes=max_bytes)
    else:
        data = await file.read()
    row = await attachments_service.create_note_attachment(
        session=session,
        storage=storage,
        user_id=int(user.id),
        note_id=note_id,
        filename=file.filename,
        content_type=file.content_type,
        data=data,
    )
    return AttachmentSchema(
        id=row.id,
        note_id=note_id,
        filename=row.filename,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        storage_key=row.storage_key,
        created_at=row.created_at,
    )


@router.get("/attachments/{attachment_id}")
async def download_attachment(
    attachment_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    storage: ObjectStorage = Depends(get_object_storage),
) -> Response:
    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user missing id",
        )

    attachment = await attachments_repo.get_attachment_active(
        session, user_id=int(user.id), attachment_id=attachment_id
    )
    if attachment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="attachment not found")

    media_type = attachment.content_type or "application/octet-stream"
    filename = attachment.filename or attachment.id

    if isinstance(storage, LocalObjectStorage):
        path = storage.resolve_path(attachment.storage_key)
        if not path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="attachment missing")
        return FileResponse(path, media_type=media_type, filename=filename)

    data = await storage.get_bytes(attachment.storage_key)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=data, media_type=media_type, headers=headers)
