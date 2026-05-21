"""User-facing email binding endpoints.

Flow:
  1. POST /api/v1/me/email/request  { email }
     -> sends a 6-digit code to the email; rate-limited per IP.
  2. POST /api/v1/me/email/confirm  { email, code }
     -> on success, stores the email on the user row + sets email_verified_at.

Both routes require the standard authenticated user (bearer or cookie+CSRF).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.config import settings
from flow_backend.db import get_session
from flow_backend.deps import get_current_user
from flow_backend.device_tracking import extract_client_ip
from flow_backend.models import User
from flow_backend.rate_limiting import build_ip_key, enforce_rate_limit
from flow_backend.schemas import EmailBindConfirmRequest, EmailBindRequest, MeResponse
from flow_backend.schemas_common import OkResponse
from flow_backend.services.email_verification_service import (
    confirm_email_verification,
    request_email_verification,
)


router = APIRouter(prefix="/me/email", tags=["me"])


@router.post("/request", response_model=OkResponse, status_code=status.HTTP_200_OK)
async def request_email_code(
    payload: EmailBindRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> OkResponse:
    ip = extract_client_ip(request)
    await enforce_rate_limit(
        scope="email_bind_request",
        key=build_ip_key(ip),
        limit=settings.email_bind_request_rate_limit_per_ip,
        window_seconds=settings.rate_limit_window_seconds,
    )

    await request_email_verification(session=session, user=user, email=payload.email, ip=ip)
    return OkResponse(ok=True)


@router.post("/confirm", response_model=MeResponse, status_code=status.HTTP_200_OK)
async def confirm_email_code(
    payload: EmailBindConfirmRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MeResponse:
    ip = extract_client_ip(request)
    await enforce_rate_limit(
        scope="email_bind_confirm",
        key=build_ip_key(ip),
        limit=settings.email_bind_confirm_rate_limit_per_ip,
        window_seconds=settings.rate_limit_window_seconds,
    )

    await confirm_email_verification(
        session=session,
        user=user,
        email=payload.email,
        code=payload.code,
    )

    # Re-fetch fresh user for response (email + email_verified_at now populated).
    fresh = await session.get(User, int(user.id) if user.id is not None else 0)
    csrf_token = getattr(request.state, "user_csrf_token", None)
    return MeResponse(
        username=(fresh.username if fresh else user.username),
        is_admin=bool(fresh.is_admin if fresh else user.is_admin),
        csrf_token=csrf_token,
        email=(fresh.email if fresh else None),
        email_verified=(fresh.email_verified_at is not None if fresh else False),
    )
