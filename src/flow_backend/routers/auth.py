from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.config import settings
from flow_backend.db import get_session
from flow_backend.memos_client import MemosClient, MemosClientError
from flow_backend.models import User
from flow_backend.schemas import LoginRequest, RegisterRequest
from flow_backend.security import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
async def register(payload: RegisterRequest, session: AsyncSession = Depends(get_session)):
    existing = (await session.exec(select(User).where(User.username == payload.username))).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username already exists")

    if settings.dev_bypass_memos:
        memos_user_id = 0
        memos_token = f"dev-{secrets.token_urlsafe(24)}"
    else:
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
            result = await client.create_user_and_token(
                create_user_endpoints=settings.create_user_endpoints_list(),
                create_token_endpoints=settings.create_token_endpoints_list(),
                username=payload.username,
                password=payload.password,
                allow_reset_existing_user_password=settings.memos_allow_reset_password_for_existing_user,
            )
            memos_user_id = result.memos_user_id
            memos_token = result.memos_token
        except MemosClientError as e:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    user = User(
        username=payload.username,
        password_hash="",
        memos_id=memos_user_id,
        memos_token=memos_token,
        is_active=True,
    )
    try:
        user.password_hash = hash_password(payload.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    try:
        session.add(user)
        await session.commit()
        await session.refresh(user)
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username already exists")

    return {"code": 200, "data": {"token": user.memos_token, "server_url": settings.memos_base_url}}


@router.post("/login")
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_session)):
    user = (await session.exec(select(User).where(User.username == payload.username))).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user disabled")

    return {"code": 200, "data": {"token": user.memos_token, "server_url": settings.memos_base_url}}


@router.post("/login_memos")
async def login_memos(payload: LoginRequest, session: AsyncSession = Depends(get_session)):
    """用“已有 Memos 账号”的用户名/密码登录，并自动换取 token。

    注意：这里的 password 是“用户在 Memos 侧真实密码”（不追加 x）。
    """
    user = (await session.exec(select(User).where(User.username == payload.username))).first()
    if user and not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user disabled")

    if settings.dev_bypass_memos:
        memos_user_id = 0
        memos_token = f"dev-{secrets.token_urlsafe(24)}"
    else:
        client = MemosClient(
            base_url=settings.memos_base_url,
            admin_token=settings.memos_admin_token,
            timeout_seconds=settings.memos_request_timeout_seconds,
        )
        try:
            result = await client.create_access_token_from_login(
                username=payload.username,
                password=payload.password,
            )
            memos_user_id = result.memos_user_id
            memos_token = result.memos_token
        except MemosClientError as e:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    try:
        password_hash = hash_password(payload.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not user:
        user = User(
            username=payload.username,
            password_hash=password_hash,
            memos_id=memos_user_id,
            memos_token=memos_token,
            is_active=True,
        )
        session.add(user)
    else:
        user.password_hash = password_hash
        user.memos_id = memos_user_id
        user.memos_token = memos_token

    try:
        await session.commit()
        await session.refresh(user)
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username already exists")

    return {"code": 200, "data": {"token": user.memos_token, "server_url": settings.memos_base_url}}
