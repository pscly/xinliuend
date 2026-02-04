from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.config import settings
from flow_backend.db import get_session, session_scope
from flow_backend.device_tracking import extract_client_ip, record_device_activity
from flow_backend.memos_client import MemosClient, MemosClientError
from flow_backend.models import User
from flow_backend.schemas import LoginRequest, RegisterRequest
from flow_backend.security import hash_password, verify_password
from flow_backend.rate_limiting import build_ip_key, build_ip_username_key, enforce_rate_limit
import flow_backend.user_session

router = APIRouter(prefix="/auth", tags=["auth"])


async def _persist_device_tracking_best_effort(user_id: int, request: Request) -> None:
    try:
        async with session_scope() as tracking_session:
            await record_device_activity(session=tracking_session, user_id=user_id, request=request)
            await tracking_session.commit()
    except Exception:
        # Device tracking must never break auth flows.
        pass


@router.post("/register")
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    ip = extract_client_ip(request)
    await enforce_rate_limit(
        scope="auth_register",
        key=build_ip_key(ip),
        limit=settings.auth_register_rate_limit_per_ip,
        window_seconds=settings.rate_limit_window_seconds,
    )

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

    user_id = user.id
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user id missing after registration",
        )

    csrf_token = secrets.token_urlsafe(24)
    flow_backend.user_session.set_user_session_cookie(response, request, int(user_id), csrf_token)

    # Best-effort: record device/IP at registration time as well.
    await _persist_device_tracking_best_effort(user_id=int(user_id), request=request)

    return {
        "code": 200,
        "data": {
            "token": user.memos_token,
            "server_url": settings.memos_base_url,
            "csrf_token": csrf_token,
        },
    }


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    ip = extract_client_ip(request)
    await enforce_rate_limit(
        scope="auth_login_ip",
        key=build_ip_key(ip),
        limit=settings.auth_login_rate_limit_per_ip,
        window_seconds=settings.rate_limit_window_seconds,
    )
    await enforce_rate_limit(
        scope="auth_login_user",
        key=build_ip_username_key(ip=ip, username=payload.username),
        limit=settings.auth_login_rate_limit_per_ip_user,
        window_seconds=settings.rate_limit_window_seconds,
    )

    user = (await session.exec(select(User).where(User.username == payload.username))).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user disabled")
    if not user.memos_token:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="memos token not set; contact admin"
        )

    user_id = user.id
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="user id missing",
        )

    csrf_token = secrets.token_urlsafe(24)
    flow_backend.user_session.set_user_session_cookie(response, request, int(user_id), csrf_token)

    # Record device/IP on login too (best-effort).
    await _persist_device_tracking_best_effort(user_id=int(user_id), request=request)

    return {
        "code": 200,
        "data": {
            "token": user.memos_token,
            "server_url": settings.memos_base_url,
            "csrf_token": csrf_token,
        },
    }


@router.post("/logout")
async def logout(request: Request):
    """Clear the user session cookie.

    - Idempotent: OK even when already logged out.
    - If a valid cookie-session exists, enforce CSRF to prevent cross-site logout.
    - Bearer-token clients should not need CSRF for this endpoint.
    """

    cookie_value = request.cookies.get(settings.user_session_cookie_name)
    session_payload = flow_backend.user_session.verify_user_session(cookie_value)
    if session_payload:
        csrf_header = request.headers.get(settings.user_csrf_header_name)
        if not csrf_header or csrf_header != session_payload.get("csrf_token"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf failed")

    resp = JSONResponse({"code": 200, "data": {"ok": True}})
    flow_backend.user_session.clear_user_session_cookie(resp)
    return resp
