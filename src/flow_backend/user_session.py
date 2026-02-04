from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

from fastapi import Request
from starlette.responses import Response

from flow_backend.config import settings


_USER_SESSION_VERSION = "v1"


def _hmac_sha256(secret: str, message: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).digest()
    # URL-safe and slightly shorter.
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _is_secure_request(request: Request) -> bool:
    # Mirrors the admin cookie secure detection.
    if settings.trust_x_forwarded_proto:
        raw = request.headers.get("x-forwarded-proto")
        if raw:
            # Take the left-most (original) scheme.
            proto = raw.split(",")[0].strip().lower()
            if proto:
                return proto == "https"
    return request.url.scheme == "https"


def make_user_session(csrf_token: str, user_id: int, now_ts: int | None = None) -> str:
    """Create a signed user session cookie value.

    Cookie format (dot-separated):
      version.exp.user_id.csrf_token.nonce.sig
    """

    now = int(now_ts if now_ts is not None else time.time())
    exp = now + int(settings.user_session_max_age_seconds)
    nonce = secrets.token_urlsafe(16)
    payload = f"{_USER_SESSION_VERSION}.{exp}.{int(user_id)}.{csrf_token}.{nonce}"
    sig = _hmac_sha256(settings.user_session_secret, payload)
    return f"{payload}.{sig}"


def verify_user_session(cookie_value: str | None, now_ts: int | None = None) -> dict | None:
    """Verify and parse a user session cookie value.

    Returns None if invalid/expired.
    Returns at least: {"user_id": int, "csrf_token": str, "exp": int}
    """

    if not cookie_value:
        return None

    parts = cookie_value.split(".")
    if len(parts) != 6:
        return None

    v, exp_s, user_id_s, csrf_token, nonce, sig = (
        parts[0],
        parts[1],
        parts[2],
        parts[3],
        parts[4],
        parts[5],
    )
    if v != _USER_SESSION_VERSION:
        return None
    if not exp_s.isdigit() or not user_id_s.isdigit():
        return None
    if not csrf_token or not nonce:
        return None

    exp = int(exp_s)
    user_id = int(user_id_s)
    now = int(now_ts if now_ts is not None else time.time())
    if exp < now:
        return None

    payload = f"{v}.{exp}.{user_id}.{csrf_token}.{nonce}"
    expected = _hmac_sha256(settings.user_session_secret, payload)
    if not secrets.compare_digest(sig, expected):
        return None

    return {"user_id": user_id, "csrf_token": csrf_token, "exp": exp}


def set_user_session_cookie(
    resp: Response, request: Request, user_id: int, csrf_token: str
) -> None:
    cookie_value = make_user_session(csrf_token=csrf_token, user_id=user_id)

    resp.set_cookie(
        key=settings.user_session_cookie_name,
        value=cookie_value,
        max_age=int(settings.user_session_max_age_seconds),
        httponly=True,
        samesite="lax",
        secure=_is_secure_request(request),
        path="/",
    )


def clear_user_session_cookie(resp: Response) -> None:
    resp.delete_cookie(
        key=settings.user_session_cookie_name,
        path="/",
    )
