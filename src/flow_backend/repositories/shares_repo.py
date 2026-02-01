from __future__ import annotations

from typing import cast

from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.models_notes import Attachment, Note, NoteAttachment, NoteShare


async def get_note_active(session: AsyncSession, *, user_id: int, note_id: str) -> Note | None:
    stmt = (
        select(Note)
        .where(Note.user_id == user_id)
        .where(Note.id == note_id)
        .where(cast(ColumnElement[object], cast(object, Note.deleted_at)).is_(None))
    )
    return (await session.exec(stmt)).first()


async def get_share_by_id(
    session: AsyncSession, *, user_id: int, share_id: str
) -> NoteShare | None:
    stmt = (
        select(NoteShare)
        .where(NoteShare.user_id == user_id)
        .where(NoteShare.id == share_id)
        .where(cast(ColumnElement[object], cast(object, NoteShare.deleted_at)).is_(None))
    )
    return (await session.exec(stmt)).first()


async def get_share_by_token(
    session: AsyncSession,
    *,
    token_prefix: str,
    token_hmac_hex: str,
) -> NoteShare | None:
    stmt = (
        select(NoteShare)
        .where(NoteShare.token_prefix == token_prefix)
        .where(NoteShare.token_hmac_hex == token_hmac_hex)
        .where(cast(ColumnElement[object], cast(object, NoteShare.deleted_at)).is_(None))
    )
    return (await session.exec(stmt)).first()


async def list_attachments_for_note(
    session: AsyncSession,
    *,
    user_id: int,
    note_id: str,
) -> list[Attachment]:
    stmt = (
        select(Attachment)
        .select_from(NoteAttachment)
        .join(
            Attachment,
            cast(ColumnElement[object], cast(object, Attachment.id))
            == cast(ColumnElement[object], cast(object, NoteAttachment.attachment_id)),
        )
        .where(NoteAttachment.user_id == user_id)
        .where(NoteAttachment.note_id == note_id)
        .where(cast(ColumnElement[object], cast(object, NoteAttachment.deleted_at)).is_(None))
        .where(cast(ColumnElement[object], cast(object, Attachment.deleted_at)).is_(None))
        .order_by(cast(ColumnElement[object], cast(object, Attachment.created_at)).asc())
    )
    return list((await session.exec(stmt)).all())


async def get_attachment_for_note(
    session: AsyncSession,
    *,
    user_id: int,
    note_id: str,
    attachment_id: str,
) -> Attachment | None:
    stmt = (
        select(Attachment)
        .select_from(NoteAttachment)
        .join(
            Attachment,
            cast(ColumnElement[object], cast(object, Attachment.id))
            == cast(ColumnElement[object], cast(object, NoteAttachment.attachment_id)),
        )
        .where(NoteAttachment.user_id == user_id)
        .where(NoteAttachment.note_id == note_id)
        .where(NoteAttachment.attachment_id == attachment_id)
        .where(cast(ColumnElement[object], cast(object, NoteAttachment.deleted_at)).is_(None))
        .where(cast(ColumnElement[object], cast(object, Attachment.deleted_at)).is_(None))
    )
    return (await session.exec(stmt)).first()
