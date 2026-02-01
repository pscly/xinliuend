"""Share management (v2, authenticated)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.db import get_session
from flow_backend.deps import get_current_user
from flow_backend.models import User
from flow_backend.services import shares_service
from flow_backend.v2.schemas.shares import ShareCreateRequest, ShareCreated

router = APIRouter()


@router.post(
    "/notes/{note_id}/shares",
    response_model=ShareCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_share(
    note_id: str,
    payload: ShareCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ShareCreated:
    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user missing id",
        )

    share_id, share_token, share_url = await shares_service.create_share(
        session=session,
        user_id=int(user.id),
        note_id=note_id,
        expires_in_seconds=payload.expires_in_seconds,
    )
    return ShareCreated(share_id=share_id, share_url=share_url, share_token=share_token)


@router.delete("/shares/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_share(
    share_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user missing id",
        )

    await shares_service.revoke_share(session=session, user_id=int(user.id), share_id=share_id)
    return None
