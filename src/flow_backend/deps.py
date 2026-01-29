from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.db import get_session
from flow_backend.device_tracking import record_device_activity
from flow_backend.models import User

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    if not creds or not creds.credentials.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing token")

    token = creds.credentials.strip()
    user = (await session.exec(select(User).where(User.memos_token == token))).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user disabled")

    # Best-effort device/IP tracking for admin dashboard.
    await record_device_activity(session=session, user_id=int(user.id), request=request)
    return user
