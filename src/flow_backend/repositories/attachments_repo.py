from __future__ import annotations

from typing import cast

from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.models_notes import Attachment, Note


async def get_note_active(session: AsyncSession, *, user_id: int, note_id: str) -> Note | None:
    stmt = (
        select(Note)
        .where(Note.user_id == user_id)
        .where(Note.id == note_id)
        .where(cast(ColumnElement[object], cast(object, Note.deleted_at)).is_(None))
    )
    return (await session.exec(stmt)).first()


async def get_attachment_active(
    session: AsyncSession, *, user_id: int, attachment_id: str
) -> Attachment | None:
    stmt = (
        select(Attachment)
        .where(Attachment.user_id == user_id)
        .where(Attachment.id == attachment_id)
        .where(cast(ColumnElement[object], cast(object, Attachment.deleted_at)).is_(None))
    )
    return (await session.exec(stmt)).first()
