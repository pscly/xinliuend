from __future__ import annotations

from typing import cast

from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.models import SyncEvent, TodoItem, TodoItemOccurrence, TodoList, UserSetting
from flow_backend.models_notes import Note


async def get_note(
    session: AsyncSession, *, user_id: int, note_id: str, include_deleted: bool
) -> Note | None:
    stmt = select(Note).where(Note.user_id == user_id).where(Note.id == note_id)
    if not include_deleted:
        stmt = stmt.where(cast(ColumnElement[object], cast(object, Note.deleted_at)).is_(None))
    return (await session.exec(stmt)).first()


async def get_todo_item(
    session: AsyncSession, *, user_id: int, item_id: str, include_deleted: bool
) -> TodoItem | None:
    stmt = select(TodoItem).where(TodoItem.user_id == user_id).where(TodoItem.id == item_id)
    if not include_deleted:
        stmt = stmt.where(cast(ColumnElement[object], cast(object, TodoItem.deleted_at)).is_(None))
    return (await session.exec(stmt)).first()


async def get_user_setting(
    session: AsyncSession, *, user_id: int, key: str, include_deleted: bool
) -> UserSetting | None:
    stmt = select(UserSetting).where(UserSetting.user_id == user_id).where(UserSetting.key == key)
    if not include_deleted:
        stmt = stmt.where(cast(ColumnElement[object], cast(object, UserSetting.deleted_at)).is_(None))
    return (await session.exec(stmt)).first()


async def get_todo_list(
    session: AsyncSession, *, user_id: int, list_id: str, include_deleted: bool
) -> TodoList | None:
    stmt = select(TodoList).where(TodoList.user_id == user_id).where(TodoList.id == list_id)
    if not include_deleted:
        stmt = stmt.where(cast(ColumnElement[object], cast(object, TodoList.deleted_at)).is_(None))
    return (await session.exec(stmt)).first()


async def get_todo_occurrence(
    session: AsyncSession, *, user_id: int, occ_id: str, include_deleted: bool
) -> TodoItemOccurrence | None:
    stmt = (
        select(TodoItemOccurrence)
        .where(TodoItemOccurrence.user_id == user_id)
        .where(TodoItemOccurrence.id == occ_id)
    )
    if not include_deleted:
        stmt = stmt.where(
            cast(ColumnElement[object], cast(object, TodoItemOccurrence.deleted_at)).is_(None)
        )
    return (await session.exec(stmt)).first()


async def list_sync_events(
    session: AsyncSession, *, user_id: int, cursor: int, limit: int
) -> tuple[list[SyncEvent], bool]:
    rows = list(
        (
            await session.exec(
                select(SyncEvent)
                .where(SyncEvent.user_id == user_id)
                .where(cast(ColumnElement[int], cast(object, SyncEvent.id)) > cursor)
                .order_by(cast(ColumnElement[object], cast(object, SyncEvent.id)).asc())
                .limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    return rows[:limit], has_more


async def get_latest_cursor(session: AsyncSession, *, user_id: int) -> int:
    result = await session.exec(
        select(SyncEvent.id)
        .where(SyncEvent.user_id == user_id)
        .order_by(cast(ColumnElement[int], cast(object, SyncEvent.id)).desc())
        .limit(1)
    )
    last = result.first()
    return int(last or 0)
