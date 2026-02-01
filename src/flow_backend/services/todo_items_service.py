from __future__ import annotations

import uuid
from typing import Any, cast

from fastapi import HTTPException, status
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.config import settings
from flow_backend.models import TodoItem, TodoList, utc_now
from flow_backend.sync_utils import clamp_client_updated_at_ms, now_ms, record_sync_event


def _new_id() -> str:
    return str(uuid.uuid4())


def _server_snapshot(*, item: TodoItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "list_id": item.list_id,
        "title": item.title,
        "tags": item.tags_json,
        "tzid": item.tzid,
        "client_updated_at_ms": item.client_updated_at_ms,
        "updated_at": item.updated_at,
        "deleted_at": item.deleted_at,
    }


def _clean_tags(tags: list[object] | None) -> list[str]:
    if not tags:
        return []
    out: list[str] = []
    for t in tags:
        s = str(t).strip()
        if s:
            out.append(s)
    return out


async def _require_list(session: AsyncSession, *, user_id: int, list_id: str) -> TodoList:
    row = (
        await session.exec(
            select(TodoList)
            .where(TodoList.user_id == user_id)
            .where(TodoList.id == list_id)
            # NOTE: v1 keeps list validity as "not deleted" only; archived lists are allowed.
            .where(cast(ColumnElement[object], cast(object, TodoList.deleted_at)).is_(None))
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="todo list not found")
    return row


async def create_item(
    *,
    session: AsyncSession,
    user_id: int,
    id_: str | None,
    list_id: str,
    title: str,
    tags: list[object],
    tzid: str | None,
    client_updated_at_ms: int | None,
) -> TodoItem:
    item_id = (id_ or "").strip() or _new_id()
    incoming_ms = clamp_client_updated_at_ms(client_updated_at_ms) or now_ms()
    tz = (tzid or "").strip() or settings.default_tzid
    tags_out = _clean_tags(tags)

    try:
        if session.in_transaction():
            await _require_list(session, user_id=user_id, list_id=list_id)
            item = TodoItem(
                id=item_id,
                user_id=user_id,
                list_id=list_id,
                title=title.strip(),
                tags_json=tags_out,
                tzid=tz,
                client_updated_at_ms=incoming_ms,
                updated_at=utc_now(),
            )
            session.add(item)
            record_sync_event(session, user_id, "todo_item", item_id, "upsert")
            await session.commit()
            return item

        async with session.begin():
            await _require_list(session, user_id=user_id, list_id=list_id)
            item = TodoItem(
                id=item_id,
                user_id=user_id,
                list_id=list_id,
                title=title.strip(),
                tags_json=tags_out,
                tzid=tz,
                client_updated_at_ms=incoming_ms,
                updated_at=utc_now(),
            )
            session.add(item)
            record_sync_event(session, user_id, "todo_item", item_id, "upsert")
            return item
    except Exception:
        try:
            await session.rollback()
        except Exception:
            pass
        raise


async def patch_item(
    *,
    session: AsyncSession,
    user_id: int,
    item_id: str,
    list_id: str | None,
    title: str | None,
    tags: list[object] | None,
    tzid: str | None,
    client_updated_at_ms: int,
) -> TodoItem:
    incoming_ms = clamp_client_updated_at_ms(client_updated_at_ms) or now_ms()

    async def _apply() -> TodoItem:
        item = (
            await session.exec(
                select(TodoItem)
                .where(TodoItem.user_id == user_id)
                .where(TodoItem.id == item_id)
                .where(cast(ColumnElement[object], cast(object, TodoItem.deleted_at)).is_(None))
            )
        ).first()
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="todo item not found")

        if incoming_ms < item.client_updated_at_ms:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "conflict",
                    "details": {"server_snapshot": _server_snapshot(item=item)},
                },
            )

        if list_id is not None:
            await _require_list(session, user_id=user_id, list_id=list_id)
            item.list_id = list_id
        if title is not None:
            item.title = title.strip()
        if tags is not None:
            item.tags_json = _clean_tags(tags)
        if tzid is not None:
            item.tzid = (tzid or "").strip() or settings.default_tzid

        item.client_updated_at_ms = incoming_ms
        item.updated_at = utc_now()
        item.deleted_at = None
        session.add(item)
        record_sync_event(session, user_id, "todo_item", item_id, "upsert")
        return item

    try:
        if session.in_transaction():
            out = await _apply()
            await session.commit()
            return out
        async with session.begin():
            return await _apply()
    except Exception:
        try:
            await session.rollback()
        except Exception:
            pass
        raise


async def delete_item(
    *,
    session: AsyncSession,
    user_id: int,
    item_id: str,
    client_updated_at_ms: int,
) -> None:
    incoming_ms = clamp_client_updated_at_ms(client_updated_at_ms) or now_ms()

    item = (
        await session.exec(
            select(TodoItem).where(TodoItem.user_id == user_id).where(TodoItem.id == item_id)
        )
    ).first()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="todo item not found")

    if incoming_ms < item.client_updated_at_ms:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "conflict",
                "details": {"server_snapshot": _server_snapshot(item=item)},
            },
        )

    item.deleted_at = utc_now()
    item.client_updated_at_ms = incoming_ms
    item.updated_at = utc_now()
    session.add(item)
    record_sync_event(session, user_id, "todo_item", item_id, "delete")
    await session.commit()


async def restore_item(
    *,
    session: AsyncSession,
    user_id: int,
    item_id: str,
    client_updated_at_ms: int,
) -> TodoItem:
    incoming_ms = clamp_client_updated_at_ms(client_updated_at_ms) or now_ms()

    item = (
        await session.exec(
            select(TodoItem).where(TodoItem.user_id == user_id).where(TodoItem.id == item_id)
        )
    ).first()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="todo item not found")

    if incoming_ms < item.client_updated_at_ms:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "conflict",
                "details": {"server_snapshot": _server_snapshot(item=item)},
            },
        )

    item.deleted_at = None
    item.client_updated_at_ms = incoming_ms
    item.updated_at = utc_now()
    session.add(item)
    record_sync_event(session, user_id, "todo_item", item_id, "upsert")
    await session.commit()
    return item
