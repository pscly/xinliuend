from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.config import settings
from flow_backend.db import get_session, session_scope
from flow_backend.device_tracking import extract_client_ip, record_device_activity
from flow_backend.memos_client import MemosClient, MemosClientError
from flow_backend.models import User, utc_now
from flow_backend.password_crypto import encrypt_password
from flow_backend.schemas import (
    AuthTokenResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    ResetPasswordResponse,
)
from flow_backend.schemas_common import OkResponse
from flow_backend.security import hash_password, verify_password
from flow_backend.rate_limiting import build_ip_key, build_ip_username_key, enforce_rate_limit
from flow_backend.services.email_service import EmailSendError, render_email, send_email
from flow_backend.services.email_verification_service import normalize_email
from flow_backend.services.password_reset_service import (
    consume_reset_token,
    create_reset_token,
)
import flow_backend.user_session


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


async def _persist_device_tracking_best_effort(user_id: int, request: Request) -> None:
    try:
        async with session_scope() as tracking_session:
            await record_device_activity(session=tracking_session, user_id=user_id, request=request)
            await tracking_session.commit()
    except Exception:
        # Device tracking must never break auth flows.
        pass


@router.post("/register", response_model=AuthTokenResponse)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> AuthTokenResponse:
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
        memos_user_name = f"users/{payload.username}"
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
            trust_env=settings.memos_http_trust_env,
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
            memos_user_name = result.memos_user_name
            memos_token = result.memos_token
        except MemosClientError as e:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    user = User(
        username=payload.username,
        password_hash="",
        memos_id=memos_user_id,
        memos_user_name=memos_user_name,
        memos_token=memos_token,
        is_active=True,
    )
    try:
        user.password_hash = hash_password(payload.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    try:
        user.password_enc = encrypt_password(payload.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
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

    return AuthTokenResponse(
        token=user.memos_token,
        server_url=settings.memos_base_url,
        csrf_token=csrf_token,
    )


@router.post("/login", response_model=AuthTokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> AuthTokenResponse:
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

    return AuthTokenResponse(
        token=user.memos_token,
        server_url=settings.memos_base_url,
        csrf_token=csrf_token,
    )


async def _send_reset_email_in_session(
    *,
    to_address: str,
    username: str,
    reset_url: str,
    ttl_minutes: int,
) -> None:
    """Background task wrapper that opens its own DB session."""

    html, text = render_email(
        "password_reset",
        {
            "brand_name": "心流（Flow）",
            "username": username,
            "reset_url": reset_url,
            "ttl_minutes": ttl_minutes,
        },
    )
    try:
        async with session_scope() as bg_session:
            await send_email(
                session=bg_session,
                to_address=to_address,
                subject="【心流 Flow】重置账号密码",
                html=html,
                text=text,
            )
    except EmailSendError as exc:
        logger.warning("forgot-password email send failed to=%s: %s", to_address, exc)
    except Exception:
        logger.exception("forgot-password email task crashed")


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    status_code=status.HTTP_200_OK,
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> ForgotPasswordResponse:
    """Issue a password-reset token and email it.

    Always returns 200 with the same body regardless of whether the email
    matches a registered+verified user. This blocks user enumeration via the
    public endpoint.
    """

    ip = extract_client_ip(request)
    await enforce_rate_limit(
        scope="auth_forgot_password",
        key=build_ip_key(ip),
        limit=settings.auth_forgot_password_rate_limit_per_ip,
        window_seconds=settings.rate_limit_window_seconds,
    )

    normalized = normalize_email(payload.email)
    if "@" in normalized and len(normalized) <= 320:
        user = (
            await session.exec(
                select(User)
                .where(User.email == normalized)
                .where(User.is_active.is_(True))  # type: ignore[union-attr]
                .where(User.email_verified_at.is_not(None))  # type: ignore[union-attr]
            )
        ).first()
        if user is not None:
            ua = request.headers.get("user-agent")
            raw_token = await create_reset_token(
                session=session,
                user=user,
                requester_ip=ip,
                requester_ua=ua,
            )
            base = settings.public_base_url.rstrip("/") or "http://localhost:31031"
            reset_url = f"{base}/reset-password?token={raw_token}"
            ttl_minutes = max(1, int(settings.password_reset_token_ttl_seconds) // 60)
            background.add_task(
                _send_reset_email_in_session,
                to_address=normalized,
                username=user.username,
                reset_url=reset_url,
                ttl_minutes=ttl_minutes,
            )

    # Always the same response — do not leak whether the email exists.
    return ForgotPasswordResponse(ok=True)


@router.post(
    "/reset-password",
    response_model=ResetPasswordResponse,
    status_code=status.HTTP_200_OK,
)
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ResetPasswordResponse:
    ip = extract_client_ip(request)
    await enforce_rate_limit(
        scope="auth_reset_password",
        key=build_ip_key(ip),
        limit=settings.auth_reset_password_rate_limit_per_ip,
        window_seconds=settings.rate_limit_window_seconds,
    )

    if payload.new_password != payload.new_password2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="两次输入的新密码不一致"
        )

    user = await consume_reset_token(session=session, raw_token=payload.token)
    if user is None or user.id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="重置链接已失效或已被使用，请重新申请",
        )

    memos_sync_warning: str | None = None
    memos_user_name = user.memos_user_name
    if not memos_user_name and user.memos_id and int(user.memos_id) > 0:
        memos_user_name = f"users/{int(user.memos_id)}"
    if (not settings.dev_bypass_memos) and memos_user_name:
        if not settings.memos_admin_token.strip():
            memos_sync_warning = "MEMOS_ADMIN_TOKEN 未配置，Memos 端密码未同步"
            logger.warning(
                "MEMOS_ADMIN_TOKEN missing during reset-password for user=%s", user.username
            )
        else:
            client = MemosClient(
                base_url=settings.memos_base_url,
                admin_token=settings.memos_admin_token,
                timeout_seconds=settings.memos_request_timeout_seconds,
                trust_env=settings.memos_http_trust_env,
            )
            try:
                await client.update_user_password(
                    user_name=memos_user_name,
                    user_id=int(user.memos_id) if user.memos_id else None,
                    new_password=payload.new_password,
                )
            except MemosClientError as e:
                memos_sync_warning = f"Memos 端密码同步失败：{e}"
                logger.warning("Memos sync failed during reset for user=%s: %s", user.username, e)

    user_row = await session.get(User, int(user.id))
    if user_row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    try:
        user_row.password_hash = hash_password(payload.new_password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    try:
        user_row.password_enc = encrypt_password(payload.new_password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    user_row.password_changed_at = utc_now()
    session.add(user_row)
    await session.commit()

    return ResetPasswordResponse(ok=True, memos_sync_warning=memos_sync_warning)


@router.post("/logout", response_model=OkResponse)
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

    resp = JSONResponse({"ok": True})
    flow_backend.user_session.clear_user_session_cookie(resp)
    return resp
