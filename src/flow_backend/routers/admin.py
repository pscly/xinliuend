from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.config import settings
from flow_backend.db import get_session
from flow_backend.device_tracking import extract_client_ip
from flow_backend.memos_client import (
    MemosClient,
    MemosClientError,
    memos_password_from_app_password,
)
from flow_backend.models import User, UserDevice, UserDeviceIP
from flow_backend.password_crypto import decrypt_password, encrypt_password
from flow_backend.rate_limiting import build_ip_key, enforce_rate_limit
from flow_backend.security import hash_password

router = APIRouter(tags=["admin"])

_BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))


def _admin_redirect(msg: str | None = None, err: str | None = None) -> RedirectResponse:
    url = "/admin"
    if msg:
        url += f"?msg={quote(msg)}"
    if err:
        sep = "&" if "?" in url else "?"
        url += f"{sep}err={quote(err)}"
    return RedirectResponse(url=url, status_code=303)


def _normalize_next_url(next_url: str | None) -> str:
    """Normalize user-provided next url to a safe in-site path.

    - Only allow absolute paths like "/admin".
    - Reject scheme-relative redirects like "//evil.com".
    """

    v = (next_url or "").strip()
    if not v:
        return "/admin"
    if not v.startswith("/"):
        return "/admin"
    if v.startswith("//"):
        return "/admin"
    return v


def _hmac_sha256(secret: str, message: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).digest()
    # URL-safe 且更短一些
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _make_admin_session_cookie_value(csrf_token: str, now_ts: int | None = None) -> str:
    now = int(now_ts if now_ts is not None else time.time())
    exp = now + int(settings.admin_session_max_age_seconds)
    nonce = secrets.token_urlsafe(16)
    payload = f"v1.{exp}.{nonce}.{csrf_token}"
    sig = _hmac_sha256(settings.admin_session_secret, payload)
    return f"{payload}.{sig}"


def _verify_admin_session_cookie(
    cookie_value: str | None, now_ts: int | None = None
) -> dict | None:
    if not cookie_value:
        return None
    parts = cookie_value.split(".")
    if len(parts) != 5:
        return None
    v, exp_s, nonce, csrf_token, sig = parts[0], parts[1], parts[2], parts[3], parts[4]
    if v != "v1":
        return None
    if not exp_s.isdigit():
        return None

    exp = int(exp_s)
    now = int(now_ts if now_ts is not None else time.time())
    if exp < now:
        return None

    payload = f"{v}.{exp}.{nonce}.{csrf_token}"
    expected = _hmac_sha256(settings.admin_session_secret, payload)
    if not secrets.compare_digest(sig, expected):
        return None

    return {"exp": exp, "csrf_token": csrf_token}


def _clear_admin_session_cookie(resp: RedirectResponse) -> None:
    resp.delete_cookie(
        key=settings.admin_session_cookie_name,
        path="/admin",
    )


def _set_admin_session_cookie(resp: RedirectResponse, csrf_token: str, request: Request) -> None:
    cookie_value = _make_admin_session_cookie_value(csrf_token=csrf_token)

    def _is_secure_request() -> bool:
        if settings.trust_x_forwarded_proto:
            raw = request.headers.get("x-forwarded-proto")
            if raw:
                # Take the left-most (original) scheme.
                proto = raw.split(",")[0].strip().lower()
                if proto:
                    return proto == "https"
        return request.url.scheme == "https"

    # SameSite=Lax + HttpOnly：兼顾易用性与安全性；
    # Secure 需要在 https 或可信反代（X-Forwarded-Proto=https）下开启。
    resp.set_cookie(
        key=settings.admin_session_cookie_name,
        value=cookie_value,
        max_age=int(settings.admin_session_max_age_seconds),
        httponly=True,
        samesite="lax",
        secure=_is_secure_request(),
        path="/admin",
    )


def _get_admin_session(request: Request) -> dict | None:
    return _verify_admin_session_cookie(request.cookies.get(settings.admin_session_cookie_name))


def _redirect_to_login(
    next_url: str = "/admin", err: str | None = None, msg: str | None = None
) -> RedirectResponse:
    url = "/admin/login"
    if next_url:
        url += f"?next={quote(next_url)}"
    if err:
        sep = "&" if "?" in url else "?"
        url += f"{sep}err={quote(err)}"
    if msg:
        sep = "&" if "?" in url else "?"
        url += f"{sep}msg={quote(msg)}"
    return RedirectResponse(url=url, status_code=303)


def _redirect_to_next(
    next_url: str | None,
    *,
    msg: str | None = None,
    err: str | None = None,
) -> RedirectResponse:
    url = _normalize_next_url(next_url)
    if msg:
        url += f"{'&' if '?' in url else '?'}msg={quote(msg)}"
    if err:
        url += f"{'&' if '?' in url else '?'}err={quote(err)}"
    return RedirectResponse(url=url, status_code=303)


def _csrf_ok(csrf_in_form: str, csrf_in_session: str) -> bool:
    return bool(csrf_in_form) and secrets.compare_digest(csrf_in_form, csrf_in_session)


@router.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    sess = _get_admin_session(request)
    if sess:
        return RedirectResponse(url="/admin", status_code=303)

    err = request.query_params.get("err")
    msg = request.query_params.get("msg")
    next_url = _normalize_next_url(request.query_params.get("next"))
    return templates.TemplateResponse(
        request=request,
        name="admin/login.html",
        context={"err": err, "msg": msg, "next": next_url},
    )


@router.post("/admin/login")
async def admin_login_submit(request: Request):
    form = await request.form()
    username = str(form.get("username") or "").strip()
    password = str(form.get("password") or "")
    next_url = _normalize_next_url(str(form.get("next") or ""))

    try:
        ip = extract_client_ip(request)
        await enforce_rate_limit(
            scope="admin_login",
            key=build_ip_key(ip),
            limit=settings.admin_login_rate_limit_per_ip,
            window_seconds=settings.rate_limit_window_seconds,
        )
    except HTTPException as e:
        if e.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            return _redirect_to_login(next_url=next_url, err="请求过于频繁，请稍后再试")
        raise

    ok_user = secrets.compare_digest(username, settings.admin_basic_user)
    ok_pass = secrets.compare_digest(password, settings.admin_basic_password)
    if not (ok_user and ok_pass):
        return _redirect_to_login(next_url=next_url, err="账号或密码错误")

    csrf_token = secrets.token_urlsafe(24)
    resp = RedirectResponse(url=next_url, status_code=303)
    _set_admin_session_cookie(resp, csrf_token=csrf_token, request=request)
    return resp


@router.post("/admin/logout")
def admin_logout(_: Request):
    resp = RedirectResponse(url="/admin/login?msg=已退出登录", status_code=303)
    _clear_admin_session_cookie(resp)
    return resp


@router.get("/admin", response_class=HTMLResponse)
async def admin_index(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    sess = _get_admin_session(request)
    if not sess:
        return _redirect_to_login(next_url="/admin")

    # SQLModel's __table__ exists at runtime but is not always visible to type checkers.
    user_table = getattr(User, "__table__", None)
    if user_table is None:
        raise RuntimeError("User.__table__ is missing")

    users = list(await session.exec(select(User).order_by(user_table.c.id.desc())))
    msg = request.query_params.get("msg")
    err = request.query_params.get("err")
    return templates.TemplateResponse(
        request=request,
        name="admin/index.html",
        context={
            "users": users,
            "memos_base_url": settings.memos_base_url,
            "msg": msg,
            "err": err,
            "csrf_token": sess["csrf_token"],
        },
    )


@router.post("/admin/users/create")
async def admin_create_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    sess = _get_admin_session(request)
    if not sess:
        return _redirect_to_login(next_url="/admin")

    form = await request.form()
    if not _csrf_ok(str(form.get("csrf_token") or ""), sess["csrf_token"]):
        resp = _redirect_to_login(next_url="/admin", err="CSRF 校验失败，请重新登录")
        _clear_admin_session_cookie(resp)
        return resp

    username = str(form.get("username") or "").strip()
    password = str(form.get("password") or "")
    password2 = str(form.get("password2") or "")
    memos_token = str(form.get("memos_token") or "").strip()
    memos_id_s = str(form.get("memos_id") or "").strip()

    if not username:
        return _admin_redirect(err="用户名不能为空")
    if len(username) > 64:
        return _admin_redirect(err="用户名太长（最多 64）")
    if not username.isalnum():
        return _admin_redirect(err="用户名只能包含字母和数字（不支持下划线）")
    if len(password) < 6:
        return _admin_redirect(err="密码太短（至少 6 位）")
    if len(password.encode("utf-8")) > 71:
        return _admin_redirect(err="密码过长（为了给 Memos 追加 x，最多 71 字节）")
    if password != password2:
        return _admin_redirect(err="两次输入的密码不一致")

    memos_id: int | None = None
    if memos_id_s:
        if not memos_id_s.isdigit():
            return _admin_redirect(err="Memos 用户 ID 必须是数字（或留空）")
        memos_id = int(memos_id_s)

    existing = (await session.exec(select(User).where(User.username == username))).first()
    if existing:
        return _admin_redirect(err="用户名已存在")

    if memos_token:
        existing_token = (
            await session.exec(select(User).where(User.memos_token == memos_token))
        ).first()
        if existing_token:
            return _admin_redirect(err="Token 已被其它用户占用")

    user = User(
        username=username,
        password_hash="",
        memos_id=memos_id,
        memos_token=memos_token or None,
        is_active=True,
    )
    try:
        user.password_hash = hash_password(password)
    except ValueError as e:
        return _admin_redirect(err=str(e))
    try:
        user.password_enc = encrypt_password(password)
    except ValueError as e:
        return _admin_redirect(err=str(e))
    try:
        session.add(user)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return _admin_redirect(err="用户名或 Token 已存在")

    return _admin_redirect(msg="创建成功")


@router.post("/admin/users/{user_id}/toggle-active")
async def toggle_active(
    user_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    sess = _get_admin_session(request)
    if not sess:
        return _redirect_to_login(next_url="/admin")

    form = await request.form()
    next_url = str(form.get("next") or "/admin")
    if not _csrf_ok(str(form.get("csrf_token") or ""), sess["csrf_token"]):
        resp = _redirect_to_login(next_url=next_url, err="CSRF 校验失败，请重新登录")
        _clear_admin_session_cookie(resp)
        return resp

    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    user.is_active = not user.is_active
    session.add(user)
    await session.commit()
    return _redirect_to_next(next_url, msg="已更新状态")


@router.post("/admin/users/{user_id}/toggle-admin")
async def toggle_admin(
    user_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    sess = _get_admin_session(request)
    if not sess:
        return _redirect_to_login(next_url="/admin")

    form = await request.form()
    next_url = str(form.get("next") or "/admin")
    if not _csrf_ok(str(form.get("csrf_token") or ""), sess["csrf_token"]):
        resp = _redirect_to_login(next_url=next_url, err="CSRF 校验失败，请重新登录")
        _clear_admin_session_cookie(resp)
        return resp

    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    user.is_admin = not user.is_admin
    session.add(user)
    await session.commit()
    return _redirect_to_next(next_url, msg="已更新管理员状态")


@router.post("/admin/users/{user_id}/delete")
async def delete_user(
    user_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    sess = _get_admin_session(request)
    if not sess:
        return _redirect_to_login(next_url="/admin")

    form = await request.form()
    next_url = str(form.get("next") or "/admin")
    if not _csrf_ok(str(form.get("csrf_token") or ""), sess["csrf_token"]):
        resp = _redirect_to_login(next_url=next_url, err="CSRF 校验失败，请重新登录")
        _clear_admin_session_cookie(resp)
        return resp

    user = await session.get(User, user_id)
    if not user:
        return _redirect_to_next(next_url, err="用户不存在")
    await session.delete(user)
    await session.commit()
    return _redirect_to_next(next_url, msg="已删除")


@router.post("/admin/users/{user_id}/set-token")
async def set_token(
    user_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    sess = _get_admin_session(request)
    if not sess:
        return _redirect_to_login(next_url="/admin")

    form = await request.form()
    next_url = str(form.get("next") or "/admin")
    if not _csrf_ok(str(form.get("csrf_token") or ""), sess["csrf_token"]):
        resp = _redirect_to_login(next_url=next_url, err="CSRF 校验失败，请重新登录")
        _clear_admin_session_cookie(resp)
        return resp

    user = await session.get(User, user_id)
    if not user:
        return _redirect_to_next(next_url, err="用户不存在")

    token = str(form.get("memos_token") or "").strip()
    memos_id_s = str(form.get("memos_id") or "").strip()
    if memos_id_s:
        if not memos_id_s.isdigit():
            return _admin_redirect(err="Memos 用户 ID 必须是数字（或留空）")
        user.memos_id = int(memos_id_s)
    else:
        user.memos_id = None

    if token:
        existing_token = (
            await session.exec(
                select(User).where((User.memos_token == token) & (User.id != user_id))
            )
        ).first()
        if existing_token:
            return _admin_redirect(err="Token 已被其它用户占用")
    user.memos_token = token or None

    try:
        session.add(user)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return _redirect_to_next(next_url, err="保存失败：用户名或 Token 冲突")
    return _redirect_to_next(next_url, msg="已保存 Token（为空则清空）")


@router.get("/admin/users/{user_id}", response_class=HTMLResponse)
async def admin_user_detail(
    user_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    sess = _get_admin_session(request)
    if not sess:
        return _redirect_to_login(next_url=f"/admin/users/{user_id}")

    user = await session.get(User, user_id)
    if not user:
        return _admin_redirect(err="用户不存在")

    msg = request.query_params.get("msg")
    err = request.query_params.get("err")
    return templates.TemplateResponse(
        request=request,
        name="admin/user_detail.html",
        context={
            "user": user,
            "memos_base_url": settings.memos_base_url,
            "csrf_token": sess["csrf_token"],
            "has_password_enc": bool(user.password_enc),
            "msg": msg,
            "err": err,
        },
    )


@router.post("/admin/users/{user_id}/secrets")
async def admin_user_secrets(
    user_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    sess = _get_admin_session(request)
    if not sess:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"ok": False, "error": "unauthorized"},
        )

    form = await request.form()
    if not _csrf_ok(str(form.get("csrf_token") or ""), sess["csrf_token"]):
        resp = JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"ok": False, "error": "CSRF 校验失败，请重新登录"},
        )
        resp.delete_cookie(key=settings.admin_session_cookie_name, path="/admin")
        return resp

    user = await session.get(User, user_id)
    if not user:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"ok": False, "error": "user not found"},
        )

    if not user.password_enc:
        return {
            "ok": False,
            "error": "该用户未记录可解密密码（旧版本数据无法恢复）；可通过重置密码写入。",
        }

    try:
        password = decrypt_password(user.password_enc)
        memos_password = memos_password_from_app_password(password)
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"ok": False, "error": str(e)},
        )
    except MemosClientError as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"ok": False, "error": str(e)},
        )

    return {"ok": True, "password": password, "memos_password": memos_password}


@router.post("/admin/users/{user_id}/reset-password")
async def admin_reset_user_password(
    user_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    sess = _get_admin_session(request)
    if not sess:
        return _redirect_to_login(next_url=f"/admin/users/{user_id}")

    form = await request.form()
    next_url = str(form.get("next") or f"/admin/users/{user_id}")
    if not _csrf_ok(str(form.get("csrf_token") or ""), sess["csrf_token"]):
        resp = _redirect_to_login(next_url=next_url, err="CSRF 校验失败，请重新登录")
        _clear_admin_session_cookie(resp)
        return resp

    password = str(form.get("password") or "")
    password2 = str(form.get("password2") or "")
    if len(password) < 6:
        return _redirect_to_next(next_url, err="密码太短（至少 6 位）")
    if len(password.encode("utf-8")) > 71:
        return _redirect_to_next(next_url, err="密码过长（为了给 Memos 追加 x，最多 71 字节）")
    if password != password2:
        return _redirect_to_next(next_url, err="两次输入的密码不一致")

    user = await session.get(User, user_id)
    if not user:
        return _redirect_to_next(next_url, err="用户不存在")

    # Best-effort keep Memos password consistent with app password (password + 'x').
    if (not settings.dev_bypass_memos) and user.memos_id and int(user.memos_id) > 0:
        if not settings.memos_admin_token.strip():
            return _redirect_to_next(next_url, err="MEMOS_ADMIN_TOKEN 未配置，无法重置 Memos 密码")
        client = MemosClient(
            base_url=settings.memos_base_url,
            admin_token=settings.memos_admin_token,
            timeout_seconds=settings.memos_request_timeout_seconds,
        )
        try:
            await client.update_user_password(user_id=int(user.memos_id), new_password=password)
        except MemosClientError as e:
            return _redirect_to_next(next_url, err=str(e))

    try:
        user.password_hash = hash_password(password)
    except ValueError as e:
        return _redirect_to_next(next_url, err=str(e))
    try:
        user.password_enc = encrypt_password(password)
    except ValueError as e:
        return _redirect_to_next(next_url, err=str(e))

    session.add(user)
    await session.commit()
    return _redirect_to_next(next_url, msg="密码已更新")


@router.get("/admin/users/{user_id}/devices", response_class=HTMLResponse)
async def admin_user_devices(
    user_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    sess = _get_admin_session(request)
    if not sess:
        return _redirect_to_login(next_url=f"/admin/users/{user_id}/devices")

    user = await session.get(User, user_id)
    if not user:
        return _admin_redirect(err="用户不存在")

    # SQLModel's __table__ exists at runtime but is not always visible to type checkers.
    user_device_table = getattr(UserDevice, "__table__")
    user_device_ip_table = getattr(UserDeviceIP, "__table__")

    devices = list(
        await session.exec(
            select(UserDevice)
            .where(UserDevice.user_id == user_id)
            .where(user_device_table.c.revoked_at.is_(None))
            .order_by(user_device_table.c.last_seen.desc())
        )
    )
    ip_rows = list(
        await session.exec(
            select(UserDeviceIP)
            .where(UserDeviceIP.user_id == user_id)
            .order_by(user_device_ip_table.c.last_seen.desc())
        )
    )
    ips_by_device_id: dict[str, list[UserDeviceIP]] = {}
    for row in ip_rows:
        ips_by_device_id.setdefault(row.device_id, []).append(row)

    now = time.time()
    active_since_ts = now - float(settings.device_active_window_seconds)

    device_views = [
        {
            "device": d,
            "online": (d.last_seen.timestamp() if d.last_seen else 0) >= active_since_ts,
            "ips": ips_by_device_id.get(d.device_id, []),
        }
        for d in devices
    ]

    return templates.TemplateResponse(
        request=request,
        name="admin/user_devices.html",
        context={
            "user": user,
            "device_views": device_views,
            "active_window_seconds": int(settings.device_active_window_seconds),
        },
    )
