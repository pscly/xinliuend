"""Notification center (v2, authenticated)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
import sqlalchemy as sa
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.db import get_session
from flow_backend.deps import get_current_user
from flow_backend.models import User
from flow_backend.models_notifications import Notification as NotificationRow
from flow_backend.models_notifications import utc_now
from flow_backend.v2.schemas.notifications import (
    Notification as NotificationSchema,
    NotificationListResponse,
    UnreadCountResponse,
)

router = APIRouter(tags=["notifications"])


@router.get("/notifications", response_model=NotificationListResponse)
async def list_notifications(
    unread_only: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> NotificationListResponse:
    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user missing id",
        )

    q = select(NotificationRow).where(NotificationRow.user_id == int(user.id))
    count_q = (
        select(sa.func.count())
        .select_from(NotificationRow)
        .where(NotificationRow.user_id == int(user.id))
    )
    if unread_only:
        q = q.where(NotificationRow.read_at.is_(None))
        count_q = count_q.where(NotificationRow.read_at.is_(None))

    q = q.order_by(NotificationRow.created_at.desc()).offset(offset).limit(limit)
    rows = list(await session.exec(q))
    total = int((await session.exec(count_q)).first() or 0)
    return NotificationListResponse(
        notifications=[
            NotificationSchema(
                id=r.id,
                kind=r.kind,
                payload=r.payload_json or {},
                created_at=r.created_at,
                read_at=r.read_at,
            )
            for r in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/notifications/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UnreadCountResponse:
    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user missing id",
        )
    q = (
        select(sa.func.count())
        .select_from(NotificationRow)
        .where(NotificationRow.user_id == int(user.id))
        .where(NotificationRow.read_at.is_(None))
    )
    unread = int((await session.exec(q)).first() or 0)
    return UnreadCountResponse(unread_count=unread)


@router.post("/notifications/{notification_id}/read", response_model=NotificationSchema)
async def mark_notification_read(
    notification_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> NotificationSchema:
    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user missing id",
        )

    row = (
        await session.exec(
            select(NotificationRow)
            .where(NotificationRow.id == notification_id)
            .where(NotificationRow.user_id == int(user.id))
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")

    if row.read_at is None:
        row.read_at = utc_now()
        row.updated_at = utc_now()
        session.add(row)
        await session.commit()
        await session.refresh(row)

    return NotificationSchema(
        id=row.id,
        kind=row.kind,
        payload=row.payload_json or {},
        created_at=row.created_at,
        read_at=row.read_at,
    )
