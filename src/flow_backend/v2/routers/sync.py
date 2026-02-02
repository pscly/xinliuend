"""Sync router (v2).

This is a minimal skeleton; implementation will follow the v2 plan.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.db import get_session
from flow_backend.deps import get_current_user
from flow_backend.models import User
from flow_backend.services import v2_sync_service
from flow_backend.v2.schemas.sync import (
    SyncChanges,
    SyncPullResponse,
    SyncPushRequest,
    SyncPushResponse,
)

router = APIRouter(tags=["sync"])


@router.get("/sync/pull", response_model=SyncPullResponse)
async def pull_sync(
    cursor: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SyncPullResponse:
    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user missing id",
        )

    data = await v2_sync_service.pull(
        session=session,
        user_id=int(user.id),
        cursor=cursor,
        limit=limit,
    )
    return SyncPullResponse(
        cursor=int(data["cursor"]),
        next_cursor=int(data["next_cursor"]),
        has_more=bool(data["has_more"]),
        changes=SyncChanges(
            notes=list(data["changes"]["notes"]),
            todo_items=list(data["changes"]["todo_items"]),
        ),
    )


@router.post("/sync/push", response_model=SyncPushResponse)
async def push_sync(
    payload: SyncPushRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SyncPushResponse:
    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user missing id",
        )

    data = await v2_sync_service.push(
        session=session,
        user_id=int(user.id),
        mutations=[m.model_dump() for m in payload.mutations],
    )
    return SyncPushResponse(
        cursor=int(data["cursor"]),
        applied=list(data["applied"]),
        rejected=list(data["rejected"]),
    )
