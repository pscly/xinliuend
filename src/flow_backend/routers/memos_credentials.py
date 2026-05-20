from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.config import settings
from flow_backend.db import get_session
from flow_backend.deps import get_current_user
from flow_backend.models import User
from flow_backend.schemas import (
    MemosCredentialIssueTokenRequest,
    MemosCredentialStatusResponse,
    MemosCredentialTokenRequest,
    MemosCredentialUpdateResponse,
)
from flow_backend.security import verify_password
from flow_backend.services.memos_credentials import (
    can_auto_issue_memos_token,
    issue_memos_personal_access_token,
    save_memos_credential,
    token_preview,
    validate_memos_token_for_user,
)
import flow_backend.user_session

router = APIRouter(prefix="/me/memos-credential", tags=["me"])


def _maybe_rotate_cookie_session_csrf(
    request: Request, response: Response, user_id: int
) -> str | None:
    # Bearer auth sets user_csrf_token to None. Cookie auth stores the current CSRF there.
    current_csrf = getattr(request.state, "user_csrf_token", None)
    if current_csrf is None:
        return None
    csrf_token = secrets.token_urlsafe(24)
    flow_backend.user_session.set_user_session_cookie(response, request, int(user_id), csrf_token)
    return csrf_token


def _credential_update_response(
    *,
    token: str,
    memos_user_id: int | None,
    memos_user_name: str,
    memos_username: str,
    csrf_token: str | None,
) -> MemosCredentialUpdateResponse:
    preview = token_preview(token)
    if preview is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="token missing"
        )
    return MemosCredentialUpdateResponse(
        ok=True,
        token=token,
        server_url=settings.memos_base_url,
        memos_user_id=memos_user_id,
        memos_user_name=memos_user_name,
        memos_username=memos_username,
        token_preview=preview,
        csrf_token=csrf_token,
    )


@router.get("", response_model=MemosCredentialStatusResponse)
async def get_memos_credential_status(
    user: User = Depends(get_current_user),
) -> MemosCredentialStatusResponse:
    return MemosCredentialStatusResponse(
        memos_base_url=settings.memos_base_url,
        has_token=bool(user.memos_token and user.memos_token.strip()),
        token_preview=token_preview(user.memos_token),
        memos_user_id=user.memos_id,
        memos_user_name=user.memos_user_name,
        can_auto_issue_token=can_auto_issue_memos_token(),
    )


@router.put("/token", response_model=MemosCredentialUpdateResponse)
async def update_memos_credential_token(
    payload: MemosCredentialTokenRequest,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MemosCredentialUpdateResponse:
    user_id = user.id
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="user id missing"
        )

    credential = await validate_memos_token_for_user(
        session=session,
        user=user,
        token=payload.memos_token,
        memos_user_id=payload.memos_user_id,
        allow_username_mismatch=False,
    )
    await save_memos_credential(session=session, user_id=int(user_id), credential=credential)
    csrf_token = _maybe_rotate_cookie_session_csrf(request, response, int(user_id))
    return _credential_update_response(
        token=credential.token,
        memos_user_id=credential.memos_user_id,
        memos_user_name=credential.memos_user_name,
        memos_username=credential.memos_username,
        csrf_token=csrf_token,
    )


@router.post("/issue-token", response_model=MemosCredentialUpdateResponse)
async def issue_memos_credential_token(
    payload: MemosCredentialIssueTokenRequest,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MemosCredentialUpdateResponse:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    user_id = user.id
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="user id missing"
        )

    credential = await issue_memos_personal_access_token(
        user=user, app_password=payload.current_password
    )
    await save_memos_credential(session=session, user_id=int(user_id), credential=credential)
    csrf_token = _maybe_rotate_cookie_session_csrf(request, response, int(user_id))
    return _credential_update_response(
        token=credential.token,
        memos_user_id=credential.memos_user_id,
        memos_user_name=credential.memos_user_name,
        memos_username=credential.memos_username,
        csrf_token=csrf_token,
    )
