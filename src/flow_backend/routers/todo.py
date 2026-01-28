from __future__ import annotations

from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.db import get_session
from flow_backend.deps import get_current_user
from flow_backend.models import TodoItem, TodoItemOccurrence, TodoList, User, utc_now
from flow_backend.schemas_todo import (
    TodoItemOccurrenceUpsertRequest,
    TodoItemPatchRequest,
    TodoItemUpsertRequest,
    TodoListPatchRequest,
    TodoListReorderItem,
    TodoListUpsertRequest,
)
from flow_backend.sync_utils import clamp_client_updated_at_ms, now_ms, record_sync_event

router = APIRouter(prefix="/todo", tags=["todo"])


def _new_id() -> str:
    return str(uuid4())


async def _require_list(session: AsyncSession, user_id: int, list_id: str) -> TodoList:
    row = (
        await session.exec(
            select(TodoList)
            .where(TodoList.user_id == user_id)
            .where(TodoList.id == list_id)
            .where(TodoList.deleted_at.is_(None))
        )
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="todo list not found")
    return row


def _apply_lww(incoming_ms: int, existing_ms: int) -> bool:
    return incoming_ms >= existing_ms


def _validate_recurring(
    is_recurring: bool, rrule: Optional[str], dtstart_local: Optional[str]
) -> None:
    if not is_recurring:
        return
    if not (rrule and rrule.strip()):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="rrule is required")
    if not (dtstart_local and dtstart_local.strip()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="dtstart_local is required"
        )


@router.get("/lists")
async def list_todo_lists(
    include_archived: bool = False,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    q = select(TodoList).where(TodoList.user_id == user.id).where(TodoList.deleted_at.is_(None))
    if not include_archived:
        q = q.where(TodoList.archived.is_(False))
    rows = list(
        await session.exec(q.order_by(TodoList.sort_order.asc(), TodoList.created_at.asc()))
    )
    data = [
        {
            "id": r.id,
            "name": r.name,
            "color": r.color,
            "sort_order": r.sort_order,
            "archived": r.archived,
            "client_updated_at_ms": r.client_updated_at_ms,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]
    return {"code": 200, "data": {"items": data}}


@router.post("/lists")
async def upsert_todo_list(
    payload: TodoListUpsertRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    list_id = payload.id or _new_id()
    incoming_ms = clamp_client_updated_at_ms(payload.client_updated_at_ms) or now_ms()

    row = (
        await session.exec(
            select(TodoList).where(TodoList.user_id == user.id).where(TodoList.id == list_id)
        )
    ).first()
    if row and not _apply_lww(incoming_ms, row.client_updated_at_ms):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="conflict (stale update)")
    if not row:
        row = TodoList(id=list_id, user_id=int(user.id), name=payload.name, client_updated_at_ms=0)

    row.name = payload.name
    row.color = payload.color
    row.sort_order = payload.sort_order
    row.archived = payload.archived
    row.client_updated_at_ms = incoming_ms
    row.updated_at = utc_now()
    row.deleted_at = None

    session.add(row)
    record_sync_event(
        session, user_id=int(user.id), resource="todo_list", entity_id=list_id, action="upsert"
    )
    await session.commit()
    await session.refresh(row)
    return {"code": 200, "data": {"id": row.id}}


@router.patch("/lists/{list_id}")
async def patch_todo_list(
    list_id: str,
    payload: TodoListPatchRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = (
        await session.exec(
            select(TodoList)
            .where(TodoList.user_id == user.id)
            .where(TodoList.id == list_id)
            .where(TodoList.deleted_at.is_(None))
        )
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="todo list not found")

    incoming_ms = clamp_client_updated_at_ms(payload.client_updated_at_ms) or now_ms()
    if not _apply_lww(incoming_ms, row.client_updated_at_ms):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="conflict (stale update)")

    if payload.name is not None:
        row.name = payload.name
    if payload.color is not None:
        row.color = payload.color
    if payload.sort_order is not None:
        row.sort_order = payload.sort_order
    if payload.archived is not None:
        row.archived = payload.archived

    row.client_updated_at_ms = incoming_ms
    row.updated_at = utc_now()

    session.add(row)
    record_sync_event(
        session, user_id=int(user.id), resource="todo_list", entity_id=list_id, action="upsert"
    )
    await session.commit()
    return {"code": 200, "data": {"ok": True}}


@router.post("/lists/reorder")
async def reorder_todo_lists(
    items: list[TodoListReorderItem],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    for it in items:
        row = (
            await session.exec(
                select(TodoList)
                .where(TodoList.user_id == user.id)
                .where(TodoList.id == it.id)
                .where(TodoList.deleted_at.is_(None))
            )
        ).first()
        if not row:
            continue
        incoming_ms = clamp_client_updated_at_ms(it.client_updated_at_ms) or now_ms()
        if not _apply_lww(incoming_ms, row.client_updated_at_ms):
            continue
        row.sort_order = it.sort_order
        row.client_updated_at_ms = incoming_ms
        row.updated_at = utc_now()
        session.add(row)
        record_sync_event(
            session, user_id=int(user.id), resource="todo_list", entity_id=row.id, action="upsert"
        )
    await session.commit()
    return {"code": 200, "data": {"ok": True}}


@router.delete("/lists/{list_id}")
async def delete_todo_list(
    list_id: str,
    client_updated_at_ms: int = Query(default=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = (
        await session.exec(
            select(TodoList).where(TodoList.user_id == user.id).where(TodoList.id == list_id)
        )
    ).first()
    if not row:
        return {"code": 200, "data": {"ok": True}}

    incoming_ms = clamp_client_updated_at_ms(client_updated_at_ms) or now_ms()
    if not _apply_lww(incoming_ms, row.client_updated_at_ms):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="conflict (stale delete)")

    row.client_updated_at_ms = incoming_ms
    row.updated_at = utc_now()
    row.deleted_at = utc_now()

    session.add(row)
    record_sync_event(
        session, user_id=int(user.id), resource="todo_list", entity_id=list_id, action="delete"
    )
    await session.commit()
    return {"code": 200, "data": {"ok": True}}


@router.get("/items")
async def list_todo_items(
    list_id: Optional[str] = None,
    status_value: Optional[str] = Query(default=None, alias="status"),
    tag: Optional[str] = None,
    include_archived_lists: bool = False,
    include_deleted: bool = False,
    limit: int = 200,
    offset: int = 0,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    q = select(TodoItem).where(TodoItem.user_id == user.id)
    if not include_deleted:
        q = q.where(TodoItem.deleted_at.is_(None))
    if list_id:
        q = q.where(TodoItem.list_id == list_id)
    if status_value:
        q = q.where(TodoItem.status == status_value)
    if tag:
        # JSON 数组查询在 SQLite/PostgreSQL 上语法不同；这里先用最小实现：返回后由客户端过滤
        pass

    if not include_archived_lists:
        active_list_ids = list(
            await session.exec(
                select(TodoList.id)
                .where(TodoList.user_id == user.id)
                .where(TodoList.deleted_at.is_(None))
                .where(TodoList.archived.is_(False))
            )
        )
        if active_list_ids:
            q = q.where(TodoItem.list_id.in_(active_list_ids))
        else:
            return {"code": 200, "data": {"items": []}}

    rows = list(
        await session.exec(
            q.order_by(TodoItem.sort_order.asc(), TodoItem.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
    )
    data = [
        {
            "id": r.id,
            "list_id": r.list_id,
            "parent_id": r.parent_id,
            "title": r.title,
            "note": r.note,
            "status": r.status,
            "priority": r.priority,
            "due_at_local": r.due_at_local,
            "completed_at_local": r.completed_at_local,
            "sort_order": r.sort_order,
            "tags": r.tags_json,
            "is_recurring": r.is_recurring,
            "rrule": r.rrule,
            "dtstart_local": r.dtstart_local,
            "tzid": r.tzid,
            "reminders": r.reminders_json,
            "client_updated_at_ms": r.client_updated_at_ms,
            "updated_at": r.updated_at,
            "deleted_at": r.deleted_at,
        }
        for r in rows
    ]
    return {"code": 200, "data": {"items": data}}


async def _upsert_item_row(
    *,
    session: AsyncSession,
    user_id: int,
    payload: TodoItemUpsertRequest,
    item_id: str,
) -> TodoItem:
    await _require_list(session, user_id=user_id, list_id=payload.list_id)
    incoming_ms = clamp_client_updated_at_ms(payload.client_updated_at_ms) or now_ms()

    row = (
        await session.exec(
            select(TodoItem).where(TodoItem.user_id == user_id).where(TodoItem.id == item_id)
        )
    ).first()
    if row and not _apply_lww(incoming_ms, row.client_updated_at_ms):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="conflict (stale update)")
    if not row:
        row = TodoItem(
            id=item_id,
            user_id=user_id,
            list_id=payload.list_id,
            title=payload.title,
            client_updated_at_ms=0,
        )

    _validate_recurring(payload.is_recurring, payload.rrule, payload.dtstart_local)

    row.list_id = payload.list_id
    row.parent_id = payload.parent_id
    row.title = payload.title
    row.note = payload.note
    row.status = payload.status
    row.priority = payload.priority
    row.due_at_local = payload.due_at_local
    row.completed_at_local = payload.completed_at_local
    row.sort_order = payload.sort_order
    row.tags_json = payload.tags
    row.is_recurring = payload.is_recurring
    row.rrule = payload.rrule.strip() if payload.rrule else None
    row.dtstart_local = payload.dtstart_local
    row.tzid = "Asia/Shanghai"
    row.reminders_json = payload.reminders
    row.client_updated_at_ms = incoming_ms
    row.updated_at = utc_now()
    row.deleted_at = None

    session.add(row)
    record_sync_event(
        session, user_id=user_id, resource="todo_item", entity_id=item_id, action="upsert"
    )
    return row


@router.post("/items")
async def upsert_todo_item(
    payload: TodoItemUpsertRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    item_id = payload.id or _new_id()
    await _upsert_item_row(session=session, user_id=int(user.id), payload=payload, item_id=item_id)
    await session.commit()
    return {"code": 200, "data": {"id": item_id}}


@router.post("/items/bulk")
async def bulk_upsert_todo_items(
    payloads: list[TodoItemUpsertRequest],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    ids: list[str] = []
    for payload in payloads:
        item_id = payload.id or _new_id()
        await _upsert_item_row(
            session=session, user_id=int(user.id), payload=payload, item_id=item_id
        )
        ids.append(item_id)
    await session.commit()
    return {"code": 200, "data": {"ids": ids}}


@router.patch("/items/{item_id}")
async def patch_todo_item(
    item_id: str,
    payload: TodoItemPatchRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = (
        await session.exec(
            select(TodoItem)
            .where(TodoItem.user_id == user.id)
            .where(TodoItem.id == item_id)
            .where(TodoItem.deleted_at.is_(None))
        )
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="todo item not found")

    incoming_ms = clamp_client_updated_at_ms(payload.client_updated_at_ms) or now_ms()
    if not _apply_lww(incoming_ms, row.client_updated_at_ms):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="conflict (stale update)")

    if payload.list_id is not None:
        await _require_list(session, user_id=int(user.id), list_id=payload.list_id)
        row.list_id = payload.list_id
    if payload.parent_id is not None:
        row.parent_id = payload.parent_id
    if payload.title is not None:
        row.title = payload.title
    if payload.note is not None:
        row.note = payload.note
    if payload.status is not None:
        row.status = payload.status
    if payload.priority is not None:
        row.priority = payload.priority
    if payload.due_at_local is not None:
        row.due_at_local = payload.due_at_local
    if payload.completed_at_local is not None:
        row.completed_at_local = payload.completed_at_local
    if payload.sort_order is not None:
        row.sort_order = payload.sort_order
    if payload.tags is not None:
        row.tags_json = payload.tags

    if payload.is_recurring is not None:
        row.is_recurring = payload.is_recurring
    if payload.rrule is not None:
        row.rrule = payload.rrule.strip() if payload.rrule else None
    if payload.dtstart_local is not None:
        row.dtstart_local = payload.dtstart_local
    if payload.tzid is not None:
        row.tzid = "Asia/Shanghai"
    if payload.reminders is not None:
        row.reminders_json = payload.reminders

    _validate_recurring(row.is_recurring, row.rrule, row.dtstart_local)

    row.client_updated_at_ms = incoming_ms
    row.updated_at = utc_now()
    session.add(row)
    record_sync_event(
        session, user_id=int(user.id), resource="todo_item", entity_id=item_id, action="upsert"
    )
    await session.commit()
    return {"code": 200, "data": {"ok": True}}


@router.delete("/items/{item_id}")
async def delete_todo_item(
    item_id: str,
    client_updated_at_ms: int = Query(default=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = (
        await session.exec(
            select(TodoItem).where(TodoItem.user_id == user.id).where(TodoItem.id == item_id)
        )
    ).first()
    if not row:
        return {"code": 200, "data": {"ok": True}}

    incoming_ms = clamp_client_updated_at_ms(client_updated_at_ms) or now_ms()
    if not _apply_lww(incoming_ms, row.client_updated_at_ms):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="conflict (stale delete)")

    row.client_updated_at_ms = incoming_ms
    row.updated_at = utc_now()
    row.deleted_at = utc_now()
    session.add(row)
    record_sync_event(
        session, user_id=int(user.id), resource="todo_item", entity_id=item_id, action="delete"
    )
    await session.commit()
    return {"code": 200, "data": {"ok": True}}


async def _upsert_occurrence_row(
    *,
    session: AsyncSession,
    user_id: int,
    payload: TodoItemOccurrenceUpsertRequest,
    occurrence_id: str,
) -> TodoItemOccurrence:
    item = (
        await session.exec(
            select(TodoItem)
            .where(TodoItem.user_id == user_id)
            .where(TodoItem.id == payload.item_id)
            .where(TodoItem.deleted_at.is_(None))
        )
    ).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="todo item not found")

    incoming_ms = clamp_client_updated_at_ms(payload.client_updated_at_ms) or now_ms()

    row = (
        await session.exec(
            select(TodoItemOccurrence)
            .where(TodoItemOccurrence.user_id == user_id)
            .where(TodoItemOccurrence.id == occurrence_id)
        )
    ).first()
    if not row and payload.id is None:
        # 若客户端没给 id，则按唯一键查找，避免重复插入
        row = (
            await session.exec(
                select(TodoItemOccurrence)
                .where(TodoItemOccurrence.user_id == user_id)
                .where(TodoItemOccurrence.item_id == payload.item_id)
                .where(TodoItemOccurrence.tzid == "Asia/Shanghai")
                .where(TodoItemOccurrence.recurrence_id_local == payload.recurrence_id_local)
            )
        ).first()
        if row:
            occurrence_id = row.id

    if row and not _apply_lww(incoming_ms, row.client_updated_at_ms):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="conflict (stale update)")
    if not row:
        row = TodoItemOccurrence(
            id=occurrence_id,
            user_id=user_id,
            item_id=payload.item_id,
            tzid="Asia/Shanghai",
            recurrence_id_local=payload.recurrence_id_local,
            client_updated_at_ms=0,
        )

    row.tzid = "Asia/Shanghai"
    row.recurrence_id_local = payload.recurrence_id_local
    row.status_override = payload.status_override
    row.title_override = payload.title_override
    row.note_override = payload.note_override
    row.due_at_override_local = payload.due_at_override_local
    row.completed_at_local = payload.completed_at_local
    row.client_updated_at_ms = incoming_ms
    row.updated_at = utc_now()
    row.deleted_at = None

    session.add(row)
    record_sync_event(
        session, user_id=user_id, resource="todo_occurrence", entity_id=row.id, action="upsert"
    )
    return row


@router.get("/occurrences")
async def list_occurrences(
    item_id: str,
    from_local: Optional[str] = Query(default=None, alias="from"),
    to_local: Optional[str] = Query(default=None, alias="to"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    q = (
        select(TodoItemOccurrence)
        .where(TodoItemOccurrence.user_id == user.id)
        .where(TodoItemOccurrence.item_id == item_id)
        .where(TodoItemOccurrence.deleted_at.is_(None))
    )
    if from_local:
        q = q.where(TodoItemOccurrence.recurrence_id_local >= from_local)
    if to_local:
        q = q.where(TodoItemOccurrence.recurrence_id_local <= to_local)
    rows = list(await session.exec(q.order_by(TodoItemOccurrence.recurrence_id_local.asc())))
    data = [
        {
            "id": r.id,
            "item_id": r.item_id,
            "tzid": r.tzid,
            "recurrence_id_local": r.recurrence_id_local,
            "status_override": r.status_override,
            "title_override": r.title_override,
            "note_override": r.note_override,
            "due_at_override_local": r.due_at_override_local,
            "completed_at_local": r.completed_at_local,
            "client_updated_at_ms": r.client_updated_at_ms,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]
    return {"code": 200, "data": {"items": data}}


@router.post("/occurrences")
async def upsert_occurrence(
    payload: TodoItemOccurrenceUpsertRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    occ_id = payload.id or _new_id()
    row = await _upsert_occurrence_row(
        session=session, user_id=int(user.id), payload=payload, occurrence_id=occ_id
    )
    await session.commit()
    return {"code": 200, "data": {"id": row.id}}


@router.post("/occurrences/bulk")
async def bulk_upsert_occurrences(
    payloads: list[TodoItemOccurrenceUpsertRequest],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    ids: list[str] = []
    for payload in payloads:
        occ_id = payload.id or _new_id()
        row = await _upsert_occurrence_row(
            session=session, user_id=int(user.id), payload=payload, occurrence_id=occ_id
        )
        ids.append(row.id)
    await session.commit()
    return {"code": 200, "data": {"ids": ids}}


@router.delete("/occurrences/{occurrence_id}")
async def delete_occurrence(
    occurrence_id: str,
    client_updated_at_ms: int = Query(default=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = (
        await session.exec(
            select(TodoItemOccurrence)
            .where(TodoItemOccurrence.user_id == user.id)
            .where(TodoItemOccurrence.id == occurrence_id)
        )
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="occurrence not found")

    incoming_ms = clamp_client_updated_at_ms(client_updated_at_ms) or now_ms()
    if not _apply_lww(incoming_ms, row.client_updated_at_ms):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="conflict (stale delete)")

    row.client_updated_at_ms = incoming_ms
    row.updated_at = utc_now()
    row.deleted_at = utc_now()
    session.add(row)
    record_sync_event(
        session, user_id=int(user.id), resource="todo_occurrence", entity_id=row.id, action="delete"
    )
    await session.commit()
    return {"code": 200, "data": {"ok": True}}
