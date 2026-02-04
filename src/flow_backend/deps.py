from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.config import settings
from flow_backend.db import get_session
from flow_backend.models import User
from flow_backend.user_session import verify_user_session

_bearer = HTTPBearer(auto_error=False)

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


async def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    # Use a dedicated session for auth so services can own tx boundaries
    # on a separate request-scoped session.
    session: AsyncSession = Depends(get_session, use_cache=False),
) -> User:
    bearer_token: str | None = None
    raw_token = creds.credentials if creds is not None else None
    if raw_token and raw_token.strip():
        bearer_token = raw_token.strip()

    had_bearer = bearer_token is not None
    if bearer_token is not None:
        token = bearer_token
        user = (await session.exec(select(User).where(User.memos_token == token))).first()
        if user:
            if not user.is_active:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user disabled")

            # Bearer auth does not use CSRF.
            request.state.user_csrf_token = None

            # Stash auth context for post-response middleware (no DB side effects here).
            user_id = user.id
            if user_id is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="user missing id"
                )
            request.state.auth_user_id = int(user_id)
            return user

    cookie_value = request.cookies.get(settings.user_session_cookie_name)
    had_cookie = bool(cookie_value)
    if had_cookie:
        session_payload = verify_user_session(cookie_value)
        if session_payload:
            request.state.user_csrf_token = session_payload.get("csrf_token")
            if request.method.upper() not in _SAFE_METHODS:
                csrf_header = request.headers.get(settings.user_csrf_header_name)
                if not csrf_header or csrf_header != session_payload.get("csrf_token"):
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf failed")

            session_user_id = int(session_payload["user_id"])
            user = (await session.exec(select(User).where(User.id == session_user_id))).first()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token"
                )
            if not user.is_active:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user disabled")

            # Stash auth context for post-response middleware (no DB side effects here).
            user_id = user.id
            if user_id is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="user missing id"
                )
            request.state.auth_user_id = int(user_id)
            return user

    if had_bearer or had_cookie:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing token")
