from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.config import settings
from flow_backend.db import get_session
from flow_backend.deps import get_current_user
from flow_backend.models import (
    SyncEvent,
    TodoItem,
    TodoItemOccurrence,
    TodoList,
    User,
    UserSetting,
    utc_now,
)
from flow_backend.schemas_sync import SyncMutation, SyncPushRequest
from flow_backend.sync_utils import clamp_client_updated_at_ms, now_ms, record_sync_event

router = APIRouter(prefix="/sync", tags=["sync"])


def _apply_lww(incoming_ms: int, existing_ms: int) -> bool:
    return incoming_ms >= existing_ms


def _serialize_setting(row: UserSetting) -> dict[str, Any]:
    return {
        "key": row.key,
        "value_json": row.value_json,
        "client_updated_at_ms": row.client_updated_at_ms,
        "updated_at": row.updated_at,
        "deleted_at": row.deleted_at,
    }


def _serialize_list(row: TodoList) -> dict[str, Any]:
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


def _serialize_item(row: TodoItem) -> dict[str, Any]:
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


def _serialize_occurrence(row: TodoItemOccurrence) -> dict[str, Any]:
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


def _sorted_mutations(mutations: list[SyncMutation]) -> list[SyncMutation]:
    order = {"user_setting": 0, "todo_list": 1, "todo_item": 2, "todo_occurrence": 3}
    return sorted(mutations, key=lambda m: order.get(m.resource, 99))


def _reject(resource: str, entity_id: str, reason: str, server: Any | None) -> dict[str, Any]:
    payload: dict[str, Any] = {"resource": resource, "entity_id": entity_id, "reason": reason}
    if server is not None:
        payload["server"] = server
    return payload


@router.post("/push")
async def push(
    req: SyncPushRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    applied: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for m in _sorted_mutations(req.mutations):
        incoming_ms = clamp_client_updated_at_ms(m.client_updated_at_ms) or now_ms()

        if m.resource == "user_setting":
            key = m.entity_id
            row = (await session.exec(
                select(UserSetting).where(UserSetting.user_id == user.id).where(UserSetting.key == key)
            )).first()
            if row and not _apply_lww(incoming_ms, row.client_updated_at_ms):
                rejected.append(_reject(m.resource, key, "conflict", _serialize_setting(row)))
                continue
            if not row:
                row = UserSetting(user_id=int(user.id), key=key, value_json={}, client_updated_at_ms=0)
            row.client_updated_at_ms = incoming_ms
            row.updated_at = utc_now()
            if m.op == "delete":
                row.deleted_at = utc_now()
            else:
                row.value_json = dict(m.data.get("value_json") or {})
                row.deleted_at = None
            session.add(row)
            record_sync_event(session, int(user.id), "user_setting", key, m.op)
            applied.append({"resource": m.resource, "entity_id": key})
            continue

        if m.resource == "todo_list":
            list_id = m.entity_id
            row = (await session.exec(
                select(TodoList).where(TodoList.user_id == user.id).where(TodoList.id == list_id)
            )).first()
            if row and not _apply_lww(incoming_ms, row.client_updated_at_ms):
                rejected.append(_reject(m.resource, list_id, "conflict", _serialize_list(row)))
                continue
            if not row:
                row = TodoList(id=list_id, user_id=int(user.id), name="tmp", client_updated_at_ms=0)

            row.client_updated_at_ms = incoming_ms
            row.updated_at = utc_now()
            if m.op == "delete":
                row.deleted_at = utc_now()
            else:
                row.name = str(m.data.get("name") or row.name)
                row.color = m.data.get("color")
                row.sort_order = int(m.data.get("sort_order") or 0)
                row.archived = bool(m.data.get("archived") or False)
                row.deleted_at = None
            session.add(row)
            record_sync_event(session, int(user.id), "todo_list", list_id, m.op)
            applied.append({"resource": m.resource, "entity_id": list_id})
            continue

        if m.resource == "todo_item":
            item_id = m.entity_id
            row = (await session.exec(
                select(TodoItem).where(TodoItem.user_id == user.id).where(TodoItem.id == item_id)
            )).first()
            if row and not _apply_lww(incoming_ms, row.client_updated_at_ms):
                rejected.append(_reject(m.resource, item_id, "conflict", _serialize_item(row)))
                continue
            if m.op == "delete" and not row:
                # 客户端可能“创建后又删除但未同步”，服务端不存在该实体时直接视为成功即可
                applied.append({"resource": m.resource, "entity_id": item_id})
                continue
            if m.op != "delete":
                list_id = str(m.data.get("list_id") or "")
                if not list_id:
                    rejected.append(_reject(m.resource, item_id, "missing list_id", None))
                    continue
                list_row = (await session.exec(
                    select(TodoList)
                    .where(TodoList.user_id == user.id)
                    .where(TodoList.id == list_id)
                    .where(TodoList.deleted_at.is_(None))
                )).first()
                if not list_row:
                    rejected.append(_reject(m.resource, item_id, "todo list not found", None))
                    continue

            if not row:
                row = TodoItem(
                    id=item_id,
                    user_id=int(user.id),
                    list_id=str(m.data.get("list_id") or ""),
                    title=str(m.data.get("title") or "tmp"),
                    client_updated_at_ms=0,
                )

            row.client_updated_at_ms = incoming_ms
            row.updated_at = utc_now()
            if m.op == "delete":
                row.deleted_at = utc_now()
            else:
                row.list_id = str(m.data.get("list_id") or row.list_id)
                row.parent_id = m.data.get("parent_id")
                row.title = str(m.data.get("title") or row.title)
                row.note = str(m.data.get("note") or "")
                row.status = str(m.data.get("status") or "open")
                row.priority = int(m.data.get("priority") or 0)
                row.due_at_local = m.data.get("due_at_local")
                row.completed_at_local = m.data.get("completed_at_local")
                row.sort_order = int(m.data.get("sort_order") or 0)
                row.tags_json = list(m.data.get("tags") or [])
                row.is_recurring = bool(m.data.get("is_recurring") or False)
                row.rrule = m.data.get("rrule")
                row.dtstart_local = m.data.get("dtstart_local")
                row.tzid = "Asia/Shanghai"
                row.reminders_json = list(m.data.get("reminders") or [])
                row.deleted_at = None
            session.add(row)
            record_sync_event(session, int(user.id), "todo_item", item_id, m.op)
            applied.append({"resource": m.resource, "entity_id": item_id})
            continue

        if m.resource == "todo_occurrence":
            occ_id = m.entity_id
            row = (await session.exec(
                select(TodoItemOccurrence)
                .where(TodoItemOccurrence.user_id == user.id)
                .where(TodoItemOccurrence.id == occ_id)
            )).first()
            if row and not _apply_lww(incoming_ms, row.client_updated_at_ms):
                rejected.append(_reject(m.resource, occ_id, "conflict", _serialize_occurrence(row)))
                continue
            if m.op == "delete" and not row:
                applied.append({"resource": m.resource, "entity_id": occ_id})
                continue

            if m.op != "delete":
                item_id = str(m.data.get("item_id") or "")
                if not item_id:
                    rejected.append(_reject(m.resource, occ_id, "missing item_id", None))
                    continue
                item = (await session.exec(
                    select(TodoItem)
                    .where(TodoItem.user_id == user.id)
                    .where(TodoItem.id == item_id)
                    .where(TodoItem.deleted_at.is_(None))
                )).first()
                if not item:
                    rejected.append(_reject(m.resource, occ_id, "todo item not found", None))
                    continue

            if not row:
                row = TodoItemOccurrence(
                    id=occ_id,
                    user_id=int(user.id),
                    item_id=str(m.data.get("item_id") or ""),
                    tzid="Asia/Shanghai",
                    recurrence_id_local=str(m.data.get("recurrence_id_local") or "1970-01-01T00:00:00"),
                    client_updated_at_ms=0,
                )

            row.client_updated_at_ms = incoming_ms
            row.updated_at = utc_now()
            if m.op == "delete":
                row.deleted_at = utc_now()
            else:
                row.item_id = str(m.data.get("item_id") or row.item_id)
                row.tzid = "Asia/Shanghai"
                row.recurrence_id_local = str(m.data.get("recurrence_id_local") or row.recurrence_id_local)
                row.status_override = m.data.get("status_override")
                row.title_override = m.data.get("title_override")
                row.note_override = m.data.get("note_override")
                row.due_at_override_local = m.data.get("due_at_override_local")
                row.completed_at_local = m.data.get("completed_at_local")
                row.deleted_at = None
            session.add(row)
            record_sync_event(session, int(user.id), "todo_occurrence", occ_id, m.op)
            applied.append({"resource": m.resource, "entity_id": occ_id})
            continue

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"unknown resource: {m.resource}")

    await session.commit()

    last_event_id = (await session.exec(
        select(SyncEvent.id)
        .where(SyncEvent.user_id == user.id)
        .order_by(SyncEvent.id.desc())
        .limit(1)
    )).first()
    cursor = int(last_event_id or 0)

    return {"code": 200, "data": {"cursor": cursor, "applied": applied, "rejected": rejected}}
