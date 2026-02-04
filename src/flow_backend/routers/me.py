from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from flow_backend.deps import get_current_user
from flow_backend.models import User

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
