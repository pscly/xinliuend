from __future__ import annotations

from typing import Annotated, Any, cast

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.db import get_session
from flow_backend.deps import get_current_user
from flow_backend.models import User
from flow_backend.models_collections import CollectionItem as CollectionItemModel
from flow_backend.schemas_common import OkResponse
from flow_backend.services import collections_service
from flow_backend.v2.schemas.collections import (
    CollectionItem as CollectionItemSchema,
    CollectionItemBatchDeleteItem,
    CollectionItemCreateRequest,
    CollectionItemList,
    CollectionItemMoveItem,
    CollectionItemPatchRequest,
    CollectionItemType,
    CollectionRefType,
)

router = APIRouter(tags=["collections"])


def _require_user_id(user: User) -> int:
    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user missing id",
        )
    return int(user.id)


def _to_schema(item: CollectionItemModel) -> CollectionItemSchema:
    if item.item_type == "folder":
        item_type: CollectionItemType = "folder"
    elif item.item_type == "note_ref":
        item_type = "note_ref"
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="invalid item_type",
        )

    if item.ref_type is None:
        ref_type: CollectionRefType | None = None
    elif item.ref_type == "flow_note":
        ref_type = "flow_note"
    elif item.ref_type == "memos_memo":
        ref_type = "memos_memo"
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="invalid ref_type",
        )

    return CollectionItemSchema(
        id=item.id,
        item_type=item_type,
        parent_id=item.parent_id,
        name=item.name,
        color=item.color,
        ref_type=ref_type,
        ref_id=item.ref_id,
        sort_order=item.sort_order,
        client_updated_at_ms=item.client_updated_at_ms,
        created_at=item.created_at,
        updated_at=item.updated_at,
        deleted_at=item.deleted_at,
    )


@router.get("/collections/items", response_model=CollectionItemList)
async def list_collection_items(
    parent_id: Annotated[str | None, Query(max_length=36)] = None,
    include_deleted: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CollectionItemList:
    user_id = _require_user_id(user)

    filters = [CollectionItemModel.user_id == user_id]
    if parent_id is not None:
        filters.append(CollectionItemModel.parent_id == parent_id)
    if not include_deleted:
        filters.append(cast(Any, CollectionItemModel.deleted_at).is_(None))

    total_stmt = select(func.count()).select_from(CollectionItemModel).where(*filters)
    total = (await session.exec(total_stmt)).one()

    stmt = (
        select(CollectionItemModel)
        .where(*filters)
        .order_by(
            cast(Any, CollectionItemModel.sort_order).asc(),
            cast(Any, CollectionItemModel.created_at).asc(),
        )
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.exec(stmt)).all()
    items = [_to_schema(r) for r in rows]
    return CollectionItemList(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/collections/items",
    response_model=CollectionItemSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_collection_item(
    payload: CollectionItemCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CollectionItemSchema:
    user_id = _require_user_id(user)

    item = await collections_service.create_collection_item(
        session, user_id=user_id, payload=payload
    )
    await session.refresh(item)
    return _to_schema(item)


@router.patch("/collections/items/move", response_model=OkResponse)
async def move_collection_items(
    items: Annotated[list[CollectionItemMoveItem], Body(embed=True)],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> OkResponse:
    user_id = _require_user_id(user)

    await collections_service.move_collection_items(session, user_id=user_id, items=items)
    return OkResponse()


# 注意：静态路径必须优先于 path param 注册，否则会被 /{item_id} 抢先匹配
@router.patch("/collections/items/{item_id}", response_model=CollectionItemSchema)
async def patch_collection_item(
    item_id: str,
    payload: CollectionItemPatchRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CollectionItemSchema:
    user_id = _require_user_id(user)

    item = await collections_service.patch_collection_item(
        session,
        user_id=user_id,
        item_id=item_id,
        payload=payload,
    )
    await session.refresh(item)
    return _to_schema(item)


@router.delete("/collections/items/{item_id}")
async def delete_collection_item(
    item_id: str,
    client_updated_at_ms: Annotated[int, Query(ge=0)],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    user_id = _require_user_id(user)

    await collections_service.delete_collection_item(
        session,
        user_id=user_id,
        item_id=item_id,
        client_updated_at_ms=client_updated_at_ms,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/collections/items/batch-delete", response_model=OkResponse)
async def batch_delete_collection_items(
    items: Annotated[list[CollectionItemBatchDeleteItem], Body(embed=True)],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> OkResponse:
    user_id = _require_user_id(user)

    for it in items:
        await collections_service.delete_collection_item(
            session,
            user_id=user_id,
            item_id=it.id,
            client_updated_at_ms=it.client_updated_at_ms,
        )

    return OkResponse()
