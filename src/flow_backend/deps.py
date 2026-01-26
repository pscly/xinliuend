from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session, select

from flow_backend.db import get_session
from flow_backend.models import User

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
) -> User:
    if not creds or not creds.credentials.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing token")

    token = creds.credentials.strip()
    user = session.exec(select(User).where(User.memos_token == token)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user disabled")
    return user

