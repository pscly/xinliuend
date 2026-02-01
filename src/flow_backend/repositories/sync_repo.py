from __future__ import annotations

from typing import cast

from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..models import SyncEvent, TodoItem, TodoItemOccurrence, TodoList, UserSetting


async def get_user_setting(session: AsyncSession, user_id: int, key: str) -> UserSetting | None:
    result = await session.exec(
        select(UserSetting).where(UserSetting.user_id == user_id).where(UserSetting.key == key)
    )
    return result.first()


async def get_todo_list(session: AsyncSession, user_id: int, list_id: str) -> TodoList | None:
    result = await session.exec(
        select(TodoList).where(TodoList.user_id == user_id).where(TodoList.id == list_id)
    )
    return result.first()


async def get_todo_list_active(
    session: AsyncSession, user_id: int, list_id: str
) -> TodoList | None:
    result = await session.exec(
        select(TodoList)
        .where(TodoList.user_id == user_id)
        .where(TodoList.id == list_id)
        .where(cast(ColumnElement[object], cast(object, TodoList.deleted_at)).is_(None))
    )
    return result.first()


async def get_todo_item(session: AsyncSession, user_id: int, item_id: str) -> TodoItem | None:
    result = await session.exec(
        select(TodoItem).where(TodoItem.user_id == user_id).where(TodoItem.id == item_id)
    )
    return result.first()


async def get_todo_item_active(
    session: AsyncSession, user_id: int, item_id: str
) -> TodoItem | None:
    result = await session.exec(
        select(TodoItem)
        .where(TodoItem.user_id == user_id)
        .where(TodoItem.id == item_id)
        .where(cast(ColumnElement[object], cast(object, TodoItem.deleted_at)).is_(None))
    )
    return result.first()


async def get_todo_occurrence(
    session: AsyncSession, user_id: int, occ_id: str
) -> TodoItemOccurrence | None:
    result = await session.exec(
        select(TodoItemOccurrence)
        .where(TodoItemOccurrence.user_id == user_id)
        .where(TodoItemOccurrence.id == occ_id)
    )
    return result.first()


async def get_todo_occurrence_active(
    session: AsyncSession, user_id: int, occ_id: str
) -> TodoItemOccurrence | None:
    result = await session.exec(
        select(TodoItemOccurrence)
        .where(TodoItemOccurrence.user_id == user_id)
        .where(TodoItemOccurrence.id == occ_id)
        .where(cast(ColumnElement[object], cast(object, TodoItemOccurrence.deleted_at)).is_(None))
    )
    return result.first()


async def get_latest_sync_event_id(session: AsyncSession, user_id: int) -> int:
    result = await session.exec(
        select(SyncEvent.id)
        .where(SyncEvent.user_id == user_id)
        .order_by(cast(ColumnElement[int], cast(object, SyncEvent.id)).desc())
        .limit(1)
    )
    last_event_id = result.first()
    return int(last_event_id or 0)
