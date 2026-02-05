from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.config import settings
from flow_backend.db import get_session
from flow_backend.deps import get_current_user
from flow_backend.models import User
from flow_backend.schemas_sync import SyncPullResponse, SyncPushRequest, SyncPushResponse
from flow_backend.services import v2_sync_service

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/pull", response_model=SyncPullResponse)
async def pull(
    cursor: int = 0,
    limit: int = Query(default=settings.sync_pull_limit, ge=1, le=1000),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    user_id = user.id
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user missing id",
        )

    data = await v2_sync_service.pull(
        session=session,
        user_id=int(user_id),
        cursor=cursor,
        limit=limit,
    )
    return data


@router.post("/push", response_model=SyncPushResponse)
async def push(
    req: SyncPushRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    user_id = user.id
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user missing id",
        )

    data = await v2_sync_service.push(
        session=session,
        user_id=int(user_id),
        mutations=[m.model_dump() for m in req.mutations],
    )
    return data
