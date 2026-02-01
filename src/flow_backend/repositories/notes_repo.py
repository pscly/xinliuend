from __future__ import annotations

from typing import cast

from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.models_notes import Note


async def get_note(
    session: AsyncSession,
    *,
    user_id: int,
    note_id: str,
    include_deleted: bool,
) -> Note | None:
    stmt = select(Note).where(Note.user_id == user_id).where(Note.id == note_id)
    if not include_deleted:
        stmt = stmt.where(cast(ColumnElement[object], cast(object, Note.deleted_at)).is_(None))
    return (await session.exec(stmt)).first()


async def get_note_active(session: AsyncSession, *, user_id: int, note_id: str) -> Note | None:
    return await get_note(session, user_id=user_id, note_id=note_id, include_deleted=False)
