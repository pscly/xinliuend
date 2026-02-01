from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.models import (
    TodoItem,
    TodoItemOccurrence,
    TodoList,
    User,
    UserSetting,
    utc_now,
)
from flow_backend.repositories import sync_repo
from flow_backend.schemas_sync import SyncMutation, SyncPushRequest
from flow_backend.sync_utils import clamp_client_updated_at_ms, now_ms, record_sync_event


def _apply_lww(incoming_ms: int, existing_ms: int) -> bool:
    return incoming_ms >= existing_ms


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


def _sorted_mutations(mutations: list[SyncMutation]) -> list[SyncMutation]:
    resource_order = {"user_setting": 0, "todo_list": 1, "todo_item": 2, "todo_occurrence": 3}
    return sorted(mutations, key=lambda m: resource_order.get(m.resource, 99))


def _reject(resource: str, entity_id: str, reason: str, server: object | None) -> dict[str, object]:
    payload: dict[str, object] = {"resource": resource, "entity_id": entity_id, "reason": reason}
    if server is not None:
        payload["server"] = server
    return payload


async def push(*, session: AsyncSession, user: User, req: SyncPushRequest) -> dict[str, Any]:
    """Apply v1 sync mutations in LWW order.

    Notes:
    - Uses a single transaction boundary (session.begin()).
    - Never commits/rollbacks explicitly; caller controls outer transaction scope.
    """

    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user id missing",
        )
    user_id = int(user.id)

    applied: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []

    async with session.begin():
        for m in _sorted_mutations(req.mutations):
            incoming_ms = clamp_client_updated_at_ms(m.client_updated_at_ms) or now_ms()

            if m.resource == "user_setting":
                key = m.entity_id
                row = await sync_repo.get_user_setting(session, user_id, key)
                if row and not _apply_lww(incoming_ms, row.client_updated_at_ms):
                    rejected.append(_reject(m.resource, key, "conflict", _serialize_setting(row)))
                    continue
                if not row:
                    row = UserSetting(
                        user_id=user_id, key=key, value_json={}, client_updated_at_ms=0
                    )

                row.client_updated_at_ms = incoming_ms
                row.updated_at = utc_now()
                if m.op == "delete":
                    row.deleted_at = utc_now()
                else:
                    row.value_json = dict(m.data.get("value_json") or {})
                    row.deleted_at = None
                session.add(row)
                record_sync_event(session, user_id, "user_setting", key, m.op)
                applied.append({"resource": m.resource, "entity_id": key})
                continue

            if m.resource == "todo_list":
                list_id = m.entity_id
                row = await sync_repo.get_todo_list(session, user_id, list_id)
                if row and not _apply_lww(incoming_ms, row.client_updated_at_ms):
                    rejected.append(_reject(m.resource, list_id, "conflict", _serialize_list(row)))
                    continue
                if not row:
                    row = TodoList(id=list_id, user_id=user_id, name="tmp", client_updated_at_ms=0)

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
                record_sync_event(session, user_id, "todo_list", list_id, m.op)
                applied.append({"resource": m.resource, "entity_id": list_id})
                continue

            if m.resource == "todo_item":
                item_id = m.entity_id
                row = await sync_repo.get_todo_item(session, user_id, item_id)
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
                    list_row = await sync_repo.get_todo_list_active(session, user_id, list_id)
                    if not list_row:
                        rejected.append(_reject(m.resource, item_id, "todo list not found", None))
                        continue

                if not row:
                    row = TodoItem(
                        id=item_id,
                        user_id=user_id,
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
                record_sync_event(session, user_id, "todo_item", item_id, m.op)
                applied.append({"resource": m.resource, "entity_id": item_id})
                continue

            if m.resource == "todo_occurrence":
                occ_id = m.entity_id
                row = await sync_repo.get_todo_occurrence(session, user_id, occ_id)
                if row and not _apply_lww(incoming_ms, row.client_updated_at_ms):
                    rejected.append(
                        _reject(m.resource, occ_id, "conflict", _serialize_occurrence(row))
                    )
                    continue
                if m.op == "delete" and not row:
                    applied.append({"resource": m.resource, "entity_id": occ_id})
                    continue

                if m.op != "delete":
                    item_id = str(m.data.get("item_id") or "")
                    if not item_id:
                        rejected.append(_reject(m.resource, occ_id, "missing item_id", None))
                        continue
                    item = await sync_repo.get_todo_item_active(session, user_id, item_id)
                    if not item:
                        rejected.append(_reject(m.resource, occ_id, "todo item not found", None))
                        continue

                if not row:
                    row = TodoItemOccurrence(
                        id=occ_id,
                        user_id=user_id,
                        item_id=str(m.data.get("item_id") or ""),
                        tzid="Asia/Shanghai",
                        recurrence_id_local=str(
                            m.data.get("recurrence_id_local") or "1970-01-01T00:00:00"
                        ),
                        client_updated_at_ms=0,
                    )

                row.client_updated_at_ms = incoming_ms
                row.updated_at = utc_now()
                if m.op == "delete":
                    row.deleted_at = utc_now()
                else:
                    row.item_id = str(m.data.get("item_id") or row.item_id)
                    row.tzid = "Asia/Shanghai"
                    row.recurrence_id_local = str(
                        m.data.get("recurrence_id_local") or row.recurrence_id_local
                    )
                    row.status_override = m.data.get("status_override")
                    row.title_override = m.data.get("title_override")
                    row.note_override = m.data.get("note_override")
                    row.due_at_override_local = m.data.get("due_at_override_local")
                    row.completed_at_local = m.data.get("completed_at_local")
                    row.deleted_at = None
                session.add(row)
                record_sync_event(session, user_id, "todo_occurrence", occ_id, m.op)
                applied.append({"resource": m.resource, "entity_id": occ_id})
                continue

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"unknown resource: {m.resource}",
            )

    cursor = await sync_repo.get_latest_sync_event_id(session, user_id)
    return {"cursor": cursor, "applied": applied, "rejected": rejected}
