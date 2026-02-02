# basedpyright: ignore
# pyright: reportUnknownArgumentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportOptionalMemberAccess=false
# pyright: reportOptionalOperand=false
# pyright: reportArgumentType=false
# pyright: reportCallInDefaultInitializer=false

"""TODO router (v2).

v2 routes are mounted at /api/v2, so these are defined without that prefix.
"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.config import settings
from flow_backend.db import get_session
from flow_backend.deps import get_current_user
from flow_backend.models import TodoItem as TodoItemRow
from flow_backend.models import TodoList, User
from flow_backend.services import todo_items_service
from flow_backend.v2.schemas.todo import (
    TodoItem as TodoItemSchema,
    TodoItemCreateRequest,
    TodoItemList,
    TodoItemPatchRequest,
    TodoItemRestoreRequest,
)

router = APIRouter(tags=["todo"])


def _is_sqlite() -> bool:
    return settings.database_url.lower().startswith("sqlite")


@router.get("/todo/items", response_model=TodoItemList)
async def list_todo_items(
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
    list_id: Annotated[str | None, Query()] = None,
    status_value: Annotated[str | None, Query(alias="status")] = None,
    tag: Annotated[str | None, Query()] = None,
    include_archived_lists: Annotated[bool, Query()] = False,
    include_deleted: Annotated[bool, Query()] = False,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TodoItemList:
    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user missing id",
        )

    q = select(TodoItemRow).where(TodoItemRow.user_id == user.id)
    count_q = select(sa.func.count()).select_from(TodoItemRow).where(TodoItemRow.user_id == user.id)

    if not include_deleted:
        q = q.where(TodoItemRow.deleted_at.is_(None))
        count_q = count_q.where(TodoItemRow.deleted_at.is_(None))
    if list_id:
        q = q.where(TodoItemRow.list_id == list_id)
        count_q = count_q.where(TodoItemRow.list_id == list_id)
    if status_value:
        q = q.where(TodoItemRow.status == status_value)
        count_q = count_q.where(TodoItemRow.status == status_value)

    if tag is not None:
        v = tag.strip()
        if v:
            if _is_sqlite():
                tag_clause = sa.text(
                    "EXISTS (SELECT 1 FROM json_each(todo_items.tags_json) WHERE json_each.value = :tag)"
                ).bindparams(tag=v)
                q = q.where(tag_clause)
                count_q = count_q.where(tag_clause)
            else:
                # Best-effort: JSON containment on Postgres.
                q = q.where(sa.cast(TodoItemRow.tags_json, postgresql.JSONB).contains([v]))
                count_q = count_q.where(
                    sa.cast(TodoItemRow.tags_json, postgresql.JSONB).contains([v])
                )

    if not include_archived_lists:
        active_list_ids = list(
            await session.exec(
                select(TodoList.id)
                .where(cast(bool, TodoList.user_id == user.id))  # pyright: ignore[reportArgumentType]
                .where(
                    cast(
                        bool,
                        cast(ColumnElement[object], cast(object, TodoList.deleted_at)).is_(None),
                    )
                )  # pyright: ignore[reportArgumentType]
                .where(cast(bool, TodoList.archived.is_(False)))  # pyright: ignore[reportArgumentType]
            )
        )
        if not active_list_ids:
            return TodoItemList(items=[], total=0, limit=limit, offset=offset)
        list_id_col = cast(ColumnElement[object], cast(object, TodoItemRow.list_id))
        q = q.where(cast(bool, list_id_col.in_(active_list_ids)))  # pyright: ignore[reportArgumentType]
        count_q = count_q.where(cast(bool, list_id_col.in_(active_list_ids)))  # pyright: ignore[reportArgumentType]

    q = (
        q.order_by(TodoItemRow.sort_order.asc(), TodoItemRow.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    rows = list(await session.exec(q))

    total = int((await session.exec(count_q)).first() or 0)

    items = [
        TodoItemSchema(
            id=r.id,
            list_id=r.list_id,
            title=r.title,
            tags=r.tags_json,
            tzid=r.tzid,
            client_updated_at_ms=r.client_updated_at_ms,
            updated_at=r.updated_at,
            deleted_at=r.deleted_at,
        )
        for r in rows
    ]
    return TodoItemList(items=items, total=total, limit=limit, offset=offset)


@router.post("/todo/items", response_model=TodoItemSchema, status_code=status.HTTP_201_CREATED)
async def create_todo_item(
    payload: TodoItemCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TodoItemSchema:
    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user missing id",
        )

    item = await todo_items_service.create_item(
        session=session,
        user_id=int(user.id),
        id_=payload.id,
        list_id=payload.list_id,
        title=payload.title,
        tags=payload.tags,
        tzid=payload.tzid,
        client_updated_at_ms=payload.client_updated_at_ms,
    )
    return TodoItemSchema(
        id=item.id,
        list_id=item.list_id,
        title=item.title,
        tags=item.tags_json,
        tzid=item.tzid,
        client_updated_at_ms=item.client_updated_at_ms,
        updated_at=item.updated_at,
        deleted_at=item.deleted_at,
    )


@router.patch("/todo/items/{item_id}", response_model=TodoItemSchema)
async def patch_todo_item(
    item_id: str,
    payload: TodoItemPatchRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TodoItemSchema:
    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user missing id",
        )

    if (
        payload.list_id is None
        and payload.title is None
        and payload.tags is None
        and payload.tzid is None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="no fields to update",
        )

    item = await todo_items_service.patch_item(
        session=session,
        user_id=int(user.id),
        item_id=item_id,
        list_id=payload.list_id,
        title=payload.title,
        tags=payload.tags,
        tzid=payload.tzid,
        client_updated_at_ms=payload.client_updated_at_ms,
    )
    return TodoItemSchema(
        id=item.id,
        list_id=item.list_id,
        title=item.title,
        tags=item.tags_json,
        tzid=item.tzid,
        client_updated_at_ms=item.client_updated_at_ms,
        updated_at=item.updated_at,
        deleted_at=item.deleted_at,
    )


@router.delete("/todo/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_todo_item(
    item_id: str,
    client_updated_at_ms: Annotated[int, Query(ge=0)],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user missing id",
        )
    await todo_items_service.delete_item(
        session=session,
        user_id=int(user.id),
        item_id=item_id,
        client_updated_at_ms=client_updated_at_ms,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/todo/items/{item_id}/restore", response_model=TodoItemSchema)
async def restore_todo_item(
    item_id: str,
    payload: TodoItemRestoreRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TodoItemSchema:
    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user missing id",
        )

    item = await todo_items_service.restore_item(
        session=session,
        user_id=int(user.id),
        item_id=item_id,
        client_updated_at_ms=payload.client_updated_at_ms,
    )
    return TodoItemSchema(
        id=item.id,
        list_id=item.list_id,
        title=item.title,
        tags=item.tags_json,
        tzid=item.tzid,
        client_updated_at_ms=item.client_updated_at_ms,
        updated_at=item.updated_at,
        deleted_at=item.deleted_at,
    )
