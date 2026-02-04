from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Request
from fastapi import HTTPException, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.config import settings
from flow_backend.db import get_session
from flow_backend.deps import get_current_user
from flow_backend.memos_client import MemosClient, MemosClientError
from flow_backend.models import User
from flow_backend.password_crypto import encrypt_password
from flow_backend.schemas import ChangePasswordRequest
from flow_backend.security import hash_password, verify_password
import flow_backend.user_session

router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
async def get_me(request: Request, user: User = Depends(get_current_user)):
    # SPA can call /me after refresh to obtain a new CSRF token without reading httpOnly cookies.
    csrf_token = getattr(request.state, "user_csrf_token", None)
    return {
        "code": 200,
        "data": {
            "username": user.username,
            "is_admin": user.is_admin,
            "csrf_token": csrf_token,
        },
    }


@router.post("/password")
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    if payload.new_password != payload.new_password2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="password mismatch")

    user_id = user.id
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="user id missing")

    if not settings.dev_bypass_memos:
        if not user.memos_token:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="memos token not set; contact admin"
            )
        if not user.memos_id or int(user.memos_id) <= 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="memos user id not set; contact admin"
            )
        if not settings.memos_admin_token.strip():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="MEMOS_ADMIN_TOKEN is not set (or set DEV_BYPASS_MEMOS=true for local dev)",
            )

        client = MemosClient(
            base_url=settings.memos_base_url,
            admin_token=settings.memos_admin_token,
            timeout_seconds=settings.memos_request_timeout_seconds,
        )
        try:
            await client.update_user_password(user_id=int(user.memos_id), new_password=payload.new_password)
        except MemosClientError as e:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    user_row = await session.get(User, int(user_id))
    if not user_row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")

    try:
        user_row.password_hash = hash_password(payload.new_password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    try:
        user_row.password_enc = encrypt_password(payload.new_password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    session.add(user_row)
    await session.commit()

    csrf_token = secrets.token_urlsafe(24)
    flow_backend.user_session.set_user_session_cookie(response, request, int(user_id), csrf_token)
    return {"code": 200, "data": {"ok": True, "csrf_token": csrf_token}}
