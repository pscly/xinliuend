from __future__ import annotations

from typing import cast

from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.models_notes import Note, NoteRevision, NoteTag, Tag


async def get_note_active(session: AsyncSession, *, user_id: int, note_id: str) -> Note | None:
    stmt = (
        select(Note)
        .where(Note.user_id == user_id)
        .where(Note.id == note_id)
        .where(cast(ColumnElement[object], cast(object, Note.deleted_at)).is_(None))
    )
    return (await session.exec(stmt)).first()


async def list_revisions(
    session: AsyncSession, *, user_id: int, note_id: str, limit: int = 100
) -> list[NoteRevision]:
    stmt = (
        select(NoteRevision)
        .where(NoteRevision.user_id == user_id)
        .where(NoteRevision.note_id == note_id)
        .where(cast(ColumnElement[object], cast(object, NoteRevision.deleted_at)).is_(None))
        .order_by(cast(ColumnElement[object], cast(object, NoteRevision.created_at)).desc())
        .limit(limit)
    )
    return list((await session.exec(stmt)).all())


async def get_revision(
    session: AsyncSession, *, user_id: int, note_id: str, revision_id: str
) -> NoteRevision | None:
    stmt = (
        select(NoteRevision)
        .where(NoteRevision.user_id == user_id)
        .where(NoteRevision.note_id == note_id)
        .where(NoteRevision.id == revision_id)
        .where(cast(ColumnElement[object], cast(object, NoteRevision.deleted_at)).is_(None))
    )
    return (await session.exec(stmt)).first()


async def list_note_tags(session: AsyncSession, *, user_id: int, note_id: str) -> list[str]:
    # Returns display names in a stable order.
    stmt = (
        select(Tag.name_original)
        .select_from(NoteTag)
        .join(
            Tag,
            cast(ColumnElement[object], cast(object, Tag.id))
            == cast(ColumnElement[object], cast(object, NoteTag.tag_id)),
        )
        .where(NoteTag.user_id == user_id)
        .where(NoteTag.note_id == note_id)
        .where(Tag.user_id == user_id)
        .where(cast(ColumnElement[object], cast(object, NoteTag.deleted_at)).is_(None))
        .where(cast(ColumnElement[object], cast(object, Tag.deleted_at)).is_(None))
        .order_by(cast(ColumnElement[object], cast(object, Tag.name_lower)).asc())
    )
    return [str(x) for x in (await session.exec(stmt)).all()]
