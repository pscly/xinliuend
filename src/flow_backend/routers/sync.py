# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportOptionalMemberAccess=false
# pyright: reportOptionalOperand=false
# pyright: reportCallInDefaultInitializer=false

"""Sync (v1) routes.

Type checking note:
SQLModel/SQLAlchemy query builder attributes like `.in_()`/`.asc()` aren't fully
understood by basedpyright in this repo.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.config import settings  # pyright: ignore[reportMissingTypeStubs]
from flow_backend.db import get_session  # pyright: ignore[reportMissingTypeStubs]
from flow_backend.deps import get_current_user  # pyright: ignore[reportMissingTypeStubs]
from flow_backend.models import (  # pyright: ignore[reportMissingTypeStubs]
    SyncEvent,
    TodoItem,
    TodoItemOccurrence,
    TodoList,
    User,
    UserSetting,
)
from flow_backend.schemas_sync import SyncPushRequest  # pyright: ignore[reportMissingTypeStubs]
from flow_backend.services import sync_service  # pyright: ignore[reportMissingTypeStubs]

router = APIRouter(prefix="/sync", tags=["sync"])


def _serialize_setting(row: UserSetting) -> dict[str, object]:
    return {
        "key": row.key,
        "value_json": row.value_json,
        "client_updated_at_ms": row.client_updated_at_ms,
        "updated_at": row.updated_at,
        "deleted_at": row.deleted_at,
    }


def _serialize_list(row: TodoList) -> dict[str, object]:
    return {
        "id": row.id,
        "name": row.name,
        "color": row.color,
        "sort_order": row.sort_order,
        "archived": row.archived,
        "client_updated_at_ms": row.client_updated_at_ms,
        "updated_at": row.updated_at,
        "deleted_at": row.deleted_at,
    }


def _serialize_item(row: TodoItem) -> dict[str, object]:
    return {
        "id": row.id,
        "list_id": row.list_id,
        "parent_id": row.parent_id,
        "title": row.title,
        "note": row.note,
        "status": row.status,
        "priority": row.priority,
        "due_at_local": row.due_at_local,
        "completed_at_local": row.completed_at_local,
        "sort_order": row.sort_order,
        "tags": row.tags_json,
        "is_recurring": row.is_recurring,
        "rrule": row.rrule,
        "dtstart_local": row.dtstart_local,
        "tzid": row.tzid,
        "reminders": row.reminders_json,
        "client_updated_at_ms": row.client_updated_at_ms,
        "updated_at": row.updated_at,
        "deleted_at": row.deleted_at,
    }


def _serialize_occurrence(row: TodoItemOccurrence) -> dict[str, object]:
    return {
        "id": row.id,
        "item_id": row.item_id,
        "tzid": row.tzid,
        "recurrence_id_local": row.recurrence_id_local,
        "status_override": row.status_override,
        "title_override": row.title_override,
        "note_override": row.note_override,
        "due_at_override_local": row.due_at_override_local,
        "completed_at_local": row.completed_at_local,
        "client_updated_at_ms": row.client_updated_at_ms,
        "updated_at": row.updated_at,
        "deleted_at": row.deleted_at,
    }


@router.get("/pull")
async def pull(
    cursor: int = 0,
    limit: int = Query(default=settings.sync_pull_limit, ge=1, le=1000),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    events = list(
        await session.exec(
            select(SyncEvent)
            .where(SyncEvent.user_id == user.id)
            .where(SyncEvent.id > cursor)
            .order_by(SyncEvent.id.asc())
            .limit(limit + 1)
        )
    )
    has_more = len(events) > limit
    events = events[:limit]

    next_cursor = cursor
    if events:
        next_cursor = int(events[-1].id or cursor)

    setting_keys: set[str] = set()
    list_ids: set[str] = set()
    item_ids: set[str] = set()
    occ_ids: set[str] = set()

    for ev in events:
        if ev.resource == "user_setting":
            setting_keys.add(ev.entity_id)
        elif ev.resource == "todo_list":
            list_ids.add(ev.entity_id)
        elif ev.resource == "todo_item":
            item_ids.add(ev.entity_id)
        elif ev.resource == "todo_occurrence":
            occ_ids.add(ev.entity_id)

    settings_rows = []
    if setting_keys:
        settings_rows = list(
            await session.exec(
                select(UserSetting)
                .where(UserSetting.user_id == user.id)
                .where(UserSetting.key.in_(sorted(setting_keys)))
            )
        )
    lists_rows = []
    if list_ids:
        lists_rows = list(
            await session.exec(
                select(TodoList)
                .where(TodoList.user_id == user.id)
                .where(TodoList.id.in_(sorted(list_ids)))
            )
        )
    items_rows = []
    if item_ids:
        items_rows = list(
            await session.exec(
                select(TodoItem)
                .where(TodoItem.user_id == user.id)
                .where(TodoItem.id.in_(sorted(item_ids)))
            )
        )
    occ_rows = []
    if occ_ids:
        occ_rows = list(
            await session.exec(
                select(TodoItemOccurrence)
                .where(TodoItemOccurrence.user_id == user.id)
                .where(TodoItemOccurrence.id.in_(sorted(occ_ids)))
            )
        )

    return {
        "code": 200,
        "data": {
            "cursor": cursor,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "changes": {
                "user_settings": [_serialize_setting(r) for r in settings_rows],
                "todo_lists": [_serialize_list(r) for r in lists_rows],
                "todo_items": [_serialize_item(r) for r in items_rows],
                "todo_occurrences": [_serialize_occurrence(r) for r in occ_rows],
            },
        },
    }


@router.post("/push")
async def push(
    req: SyncPushRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    data = await sync_service.push(session=session, user=user, req=req)
    return {"code": 200, "data": data}
