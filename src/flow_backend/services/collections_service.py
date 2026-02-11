from __future__ import annotations

import uuid
from typing import Any, cast

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.models_collections import CollectionItem, utc_now
from flow_backend.sync_utils import clamp_client_updated_at_ms, now_ms, record_sync_event
from flow_backend.v2.schemas.collections import (
    CollectionItemCreateRequest,
    CollectionItemMoveItem,
    CollectionItemPatchRequest,
)


def _new_id() -> str:
    return str(uuid.uuid4())


def _server_snapshot(*, item: CollectionItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "item_type": item.item_type,
        "parent_id": item.parent_id,
        "name": item.name,
        "color": item.color,
        "ref_type": item.ref_type,
        "ref_id": item.ref_id,
        "sort_order": item.sort_order,
        "client_updated_at_ms": item.client_updated_at_ms,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "deleted_at": item.deleted_at,
    }


def _assert_item_semantics(item: CollectionItem) -> None:
    if item.item_type == "folder":
        if item.name.strip() == "":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name is required")
        if item.ref_type is not None or item.ref_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ref_type/ref_id must be None for folder",
            )
        return

    if item.item_type == "note_ref":
        if item.ref_type is None or item.ref_id is None or item.ref_id.strip() == "":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ref_type and ref_id are required for note_ref",
            )
        return

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="invalid item_type",
    )


async def create_collection_item(
    session: AsyncSession,
    *,
    user_id: int,
    payload: CollectionItemCreateRequest,
) -> CollectionItem:
    item_id = (payload.id or "").strip() or _new_id()
    incoming_ms = clamp_client_updated_at_ms(payload.client_updated_at_ms) or now_ms()
    now = utc_now()

    item = CollectionItem(
        id=item_id,
        user_id=user_id,
        item_type=payload.item_type,
        parent_id=payload.parent_id,
        name=payload.name or "",
        color=payload.color,
        ref_type=payload.ref_type,
        ref_id=payload.ref_id,
        sort_order=payload.sort_order or 0,
        client_updated_at_ms=incoming_ms,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )
    _assert_item_semantics(item)

    try:
        if session.in_transaction():
            session.add(item)
            record_sync_event(session, user_id, "collection_item", item.id, "upsert")
            await session.commit()
            return item

        async with session.begin():
            session.add(item)
            record_sync_event(session, user_id, "collection_item", item.id, "upsert")
            return item
    except IntegrityError:
        try:
            await session.rollback()
        except Exception:
            pass
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="item already exists")
    except Exception:
        try:
            await session.rollback()
        except Exception:
            pass
        raise


async def patch_collection_item(
    session: AsyncSession,
    *,
    user_id: int,
    item_id: str,
    payload: CollectionItemPatchRequest,
) -> CollectionItem:
    incoming_ms = clamp_client_updated_at_ms(payload.client_updated_at_ms) or now_ms()

    async def _apply() -> CollectionItem:
        item = (
            await session.exec(
                select(CollectionItem)
                .where(CollectionItem.user_id == user_id)
                .where(CollectionItem.id == item_id)
                .where(
                    cast(ColumnElement[object], cast(object, CollectionItem.deleted_at)).is_(None)
                )
            )
        ).first()
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item not found")

        if incoming_ms < item.client_updated_at_ms:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "conflict",
                    "details": {"server_snapshot": _server_snapshot(item=item)},
                },
            )

        changed = set(payload.model_fields_set)
        if "parent_id" in changed:
            item.parent_id = payload.parent_id

        if "name" in changed:
            if payload.name is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="name cannot be null"
                )
            item.name = payload.name

        if "color" in changed:
            item.color = payload.color

        if "sort_order" in changed:
            if payload.sort_order is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="sort_order cannot be null",
                )
            item.sort_order = payload.sort_order

        if "ref_type" in changed or "ref_id" in changed:
            if item.item_type != "note_ref":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="ref_type/ref_id can only be patched for note_ref",
                )
            if payload.ref_type is None or payload.ref_id is None or payload.ref_id.strip() == "":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="ref_type/ref_id cannot be cleared",
                )
            item.ref_type = payload.ref_type
            item.ref_id = payload.ref_id

        item.client_updated_at_ms = incoming_ms
        item.updated_at = utc_now()
        item.deleted_at = None
        _assert_item_semantics(item)

        session.add(item)
        record_sync_event(session, user_id, "collection_item", item.id, "upsert")
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


async def delete_collection_item(
    session: AsyncSession,
    *,
    user_id: int,
    item_id: str,
    client_updated_at_ms: int,
) -> None:
    incoming_ms = clamp_client_updated_at_ms(client_updated_at_ms) or now_ms()

    async def _apply() -> None:
        root = (
            await session.exec(
                select(CollectionItem)
                .where(CollectionItem.user_id == user_id)
                .where(CollectionItem.id == item_id)
            )
        ).first()
        if root is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item not found")

        if incoming_ms < root.client_updated_at_ms:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "conflict",
                    "details": {"server_snapshot": _server_snapshot(item=root)},
                },
            )

        now = utc_now()

        if root.item_type == "note_ref":
            root.deleted_at = now
            root.client_updated_at_ms = incoming_ms
            root.updated_at = now
            session.add(root)
            record_sync_event(session, user_id, "collection_item", root.id, "delete")
            return

        if root.item_type != "folder":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="invalid item_type",
            )

        visited: set[str] = {root.id}
        frontier: list[str] = [root.id]
        to_tombstone: list[CollectionItem] = [root]

        while frontier:
            children = (
                await session.exec(
                    select(CollectionItem)
                    .where(CollectionItem.user_id == user_id)
                    .where(
                        cast(ColumnElement[object], cast(object, CollectionItem.parent_id)).in_(
                            frontier
                        )
                    )
                )
            ).all()

            next_frontier: list[str] = []
            for child in children:
                if child.id in visited:
                    continue
                visited.add(child.id)
                next_frontier.append(child.id)
                to_tombstone.append(child)
            frontier = next_frontier

        for row in to_tombstone:
            row.deleted_at = now
            row.updated_at = now
            row.client_updated_at_ms = max(row.client_updated_at_ms, incoming_ms)
            session.add(row)
            record_sync_event(session, user_id, "collection_item", row.id, "delete")

    try:
        if session.in_transaction():
            await _apply()
            await session.commit()
            return

        async with session.begin():
            await _apply()
    except Exception:
        try:
            await session.rollback()
        except Exception:
            pass
        raise


async def move_collection_items(
    session: AsyncSession,
    *,
    user_id: int,
    items: list[CollectionItemMoveItem],
) -> None:
    if not items:
        return

    item_ids = [it.id for it in items]
    if len(set(item_ids)) != len(item_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="duplicate item ids in request",
        )

    def _normalize_incoming_ms(ms: int) -> int:
        return clamp_client_updated_at_ms(ms) or now_ms()

    incoming_ms_by_id: dict[str, int] = {
        it.id: _normalize_incoming_ms(it.client_updated_at_ms) for it in items
    }

    parent_ids = {it.parent_id for it in items if it.parent_id is not None}

    async def _assert_no_descendant_parent(*, folder_id: str, target_parent_id: str) -> None:
        visited: set[str] = {folder_id}
        frontier: list[str] = [folder_id]

        while frontier:
            children = (
                await session.exec(
                    select(CollectionItem)
                    .where(CollectionItem.user_id == user_id)
                    .where(
                        cast(ColumnElement[object], cast(object, CollectionItem.parent_id)).in_(
                            frontier
                        )
                    )
                )
            ).all()

            next_frontier: list[str] = []
            for child in children:
                if child.id == target_parent_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="cannot move folder under its descendant",
                    )
                if child.id in visited:
                    continue
                visited.add(child.id)
                next_frontier.append(child.id)
            frontier = next_frontier

    async def _apply() -> None:
        rows = (
            await session.exec(
                select(CollectionItem)
                .where(CollectionItem.user_id == user_id)
                .where(cast(ColumnElement[object], cast(object, CollectionItem.id)).in_(item_ids))
                .where(
                    cast(ColumnElement[object], cast(object, CollectionItem.deleted_at)).is_(None)
                )
            )
        ).all()
        by_id = {r.id: r for r in rows}

        for it in items:
            row = by_id.get(it.id)
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item not found")

            incoming_ms = incoming_ms_by_id[it.id]
            if incoming_ms < row.client_updated_at_ms:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "message": "conflict",
                        "details": {
                            "entity_id": row.id,
                            "server_snapshot": _server_snapshot(item=row),
                        },
                    },
                )

        parents_by_id: dict[str, CollectionItem] = {}
        if parent_ids:
            parent_rows = (
                await session.exec(
                    select(CollectionItem)
                    .where(CollectionItem.user_id == user_id)
                    .where(
                        cast(ColumnElement[object], cast(object, CollectionItem.id)).in_(
                            list(parent_ids)
                        )
                    )
                    .where(
                        cast(ColumnElement[object], cast(object, CollectionItem.deleted_at)).is_(
                            None
                        )
                    )
                )
            ).all()
            parents_by_id = {p.id: p for p in parent_rows}

        for it in items:
            if it.parent_id is None:
                continue

            parent = parents_by_id.get(it.parent_id)
            if parent is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="parent not found"
                )
            if parent.user_id != user_id or parent.item_type != "folder":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="parent must be an active folder",
                )

        for it in items:
            row = by_id[it.id]
            if row.item_type != "folder":
                continue
            if it.parent_id is None:
                continue
            if it.parent_id == row.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="cannot set parent_id to self",
                )
            await _assert_no_descendant_parent(folder_id=row.id, target_parent_id=it.parent_id)

        now = utc_now()
        for it in items:
            row = by_id[it.id]
            row.parent_id = it.parent_id
            row.sort_order = it.sort_order
            row.client_updated_at_ms = incoming_ms_by_id[it.id]
            row.updated_at = now
            session.add(row)
            record_sync_event(session, user_id, "collection_item", row.id, "upsert")

    try:
        if session.in_transaction():
            await _apply()
            await session.commit()
            return

        async with session.begin():
            await _apply()
    except Exception:
        try:
            await session.rollback()
        except Exception:
            pass
        raise
