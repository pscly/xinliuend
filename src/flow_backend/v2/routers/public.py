"""Public (anonymous) routes for share links (v2)."""

from __future__ import annotations

import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.config import settings
from flow_backend.device_tracking import extract_client_ip
from flow_backend.db import get_session
from flow_backend.integrations.storage.local_storage import LocalObjectStorage
from flow_backend.integrations.storage.object_storage import ObjectStorage, get_object_storage
from flow_backend.http_headers import build_content_disposition_attachment, sanitize_filename
from flow_backend.models import User
from flow_backend.models_notifications import Notification
from flow_backend.rate_limiting import build_ip_key, enforce_rate_limit
from flow_backend.services import attachments_service
from flow_backend.services import shares_service
from flow_backend.v2.schemas.comments import (
    PublicShareComment as PublicShareCommentSchema,
    PublicShareCommentCreateRequest,
    PublicShareCommentListResponse,
)
from flow_backend.v2.schemas.notes import Note as NoteSchema
from flow_backend.v2.schemas.shares import SharedAttachment, SharedNote

router = APIRouter(tags=["public"])


_MENTION_RE = re.compile(r"@([A-Za-z0-9]{1,64})")


def _extract_mentions(*, body: str) -> set[str]:
    # Note: this intentionally stays simple (no unicode, no underscores).
    return set(_MENTION_RE.findall(body or ""))


def _build_snippet(*, body: str, max_len: int = 160) -> str:
    s = (body or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 3].rstrip() + "..."


async def _read_upload_file_limited(*, file: UploadFile, max_bytes: int) -> bytes:
    # Mirror private upload behavior.
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


def _is_captcha_token_valid(*, token: str) -> bool:
    t = (token or "").strip()
    if not t:
        return False
    if settings.environment.strip().lower() == "production":
        # Placeholder: in production we only enforce presence until a real provider is wired.
        return True
    if t == "test-pass":
        return True
    if t in {"test-fail", "invalid"}:
        return False
    return True


def _require_captcha_or_400(*, token: str | None) -> None:
    if not token or not _is_captcha_token_valid(token=token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "captcha required", "details": {"header": "X-Captcha-Token"}},
        )


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


@router.get(
    "/public/shares/{share_token}/comments",
    response_model=PublicShareCommentListResponse,
)
async def list_shared_comments(
    share_token: str,
    session: AsyncSession = Depends(get_session),
) -> PublicShareCommentListResponse:
    _share, rows = await shares_service.list_public_share_comments(
        session=session, share_token=share_token
    )
    return PublicShareCommentListResponse(
        comments=[
            PublicShareCommentSchema(
                id=r.id,
                body=r.body,
                author_name=r.author_name,
                attachment_ids=list(r.attachment_ids_json or []),
                is_folded=bool(r.is_folded),
                folded_reason=r.folded_reason,
                created_at=r.created_at,
            )
            for r in rows
        ]
    )


@router.post(
    "/public/shares/{share_token}/comments",
    response_model=PublicShareCommentSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_shared_comment(
    share_token: str,
    payload: PublicShareCommentCreateRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> PublicShareCommentSchema:
    share, _note = await shares_service.resolve_share_and_note_for_public(
        session=session, share_token=share_token
    )
    if not share.allow_anonymous_comments:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="anonymous comments disabled"
        )

    ip = extract_client_ip(request)
    await enforce_rate_limit(
        scope="public_share_comment",
        key=build_ip_key(ip),
        limit=30,
        window_seconds=settings.rate_limit_window_seconds,
    )

    if share.anonymous_comments_require_captcha:
        token = request.headers.get("X-Captcha-Token") or payload.captcha_token
        _require_captcha_or_400(token=token)

    row = await shares_service.create_public_share_comment(
        session=session,
        share_token=share_token,
        body=payload.body,
        author_name=payload.author_name,
        attachment_ids=payload.attachment_ids,
    )

    # Mention notifications (best-effort): only after comment creation succeeds.
    usernames = _extract_mentions(body=row.body)
    if usernames:
        users = list(
            (
                await session.exec(
                    select(User).where(User.username.in_(sorted(usernames)))  # type: ignore[arg-type]
                )
            ).all()
        )
        notifications = []
        for u in users:
            if u.id is None:
                continue
            notifications.append(
                Notification(
                    id=str(uuid.uuid4()),
                    user_id=int(u.id),
                    kind="mention",
                    payload_json={
                        "share_token": share_token,
                        "note_id": share.note_id,
                        "comment_id": row.id,
                        "snippet": _build_snippet(body=row.body),
                    },
                )
            )
        if notifications:
            try:
                for n in notifications:
                    session.add(n)
                await session.commit()
            except Exception:
                try:
                    await session.rollback()
                except Exception:
                    pass

    return PublicShareCommentSchema(
        id=row.id,
        body=row.body,
        author_name=row.author_name,
        attachment_ids=list(row.attachment_ids_json or []),
        is_folded=bool(row.is_folded),
        folded_reason=row.folded_reason,
        created_at=row.created_at,
    )


@router.post(
    "/public/shares/{share_token}/comments/{comment_id}/report",
    response_model=PublicShareCommentSchema,
)
async def report_shared_comment(
    share_token: str,
    comment_id: str,
    session: AsyncSession = Depends(get_session),
) -> PublicShareCommentSchema:
    row = await shares_service.report_public_share_comment(
        session=session, share_token=share_token, comment_id=comment_id
    )
    return PublicShareCommentSchema(
        id=row.id,
        body=row.body,
        author_name=row.author_name,
        attachment_ids=list(row.attachment_ids_json or []),
        is_folded=bool(row.is_folded),
        folded_reason=row.folded_reason,
        created_at=row.created_at,
    )


@router.post(
    "/public/shares/{share_token}/attachments",
    response_model=SharedAttachment,
    status_code=status.HTTP_201_CREATED,
)
async def upload_shared_attachment(
    share_token: str,
    file: Annotated[UploadFile, File()],
    request: Request,
    session: AsyncSession = Depends(get_session),
    storage: ObjectStorage = Depends(get_object_storage),
) -> SharedAttachment:
    share, _note = await shares_service.resolve_share_and_note_for_public(
        session=session, share_token=share_token
    )
    if not share.allow_anonymous_comments:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="anonymous comments disabled"
        )

    if share.anonymous_comments_require_captcha:
        # Multipart form: accept captcha only via header.
        token = request.headers.get("X-Captcha-Token")
        _require_captcha_or_400(token=token)

    ip = extract_client_ip(request)
    await enforce_rate_limit(
        scope="public_share_upload",
        key=build_ip_key(ip),
        limit=20,
        window_seconds=settings.rate_limit_window_seconds,
    )

    max_bytes = int(settings.attachments_max_size_bytes)
    if max_bytes > 0:
        data = await _read_upload_file_limited(file=file, max_bytes=max_bytes)
    else:
        data = await file.read()

    row = await attachments_service.create_note_attachment(
        session=session,
        storage=storage,
        user_id=share.user_id,
        note_id=share.note_id,
        filename=file.filename,
        content_type=file.content_type,
        data=data,
    )
    return SharedAttachment(
        id=row.id,
        filename=row.filename,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
    )


@router.get(
    "/public/shares/{share_token}/attachments/{attachment_id}",
    response_class=Response,
    responses={
        200: {
            "description": "Shared attachment content (bytes).",
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"},
                }
            },
            "headers": {
                "Content-Disposition": {
                    "schema": {"type": "string"},
                    "description": "Best-effort attachment filename.",
                }
            },
        }
    },
)
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
