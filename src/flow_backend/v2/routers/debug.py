"""Debug router (v2).

This router is only included when ENVIRONMENT != production.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.db import get_session
from flow_backend.deps import get_current_user
from flow_backend.models import User, UserSetting

router = APIRouter()


class TxFailRequest(BaseModel):
    key: str


@router.post("/debug/tx-fail")
async def tx_fail(
    payload: TxFailRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    # Force a DB write then crash, to verify the request transaction rolls back.
    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="user missing id"
        )

    session.add(
        UserSetting(
            user_id=int(user.id),
            key=payload.key,
            value_json={
                "source": "tx-fail",
                "request_id": getattr(request.state, "request_id", None),
            },
        )
    )
    await session.flush()
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="intentional tx failure"
    )
