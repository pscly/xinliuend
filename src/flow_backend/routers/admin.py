from __future__ import annotations

import secrets
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from flow_backend.config import settings
from flow_backend.db import get_session
from flow_backend.memos_client import MemosClient, MemosClientError
from flow_backend.models import User
from flow_backend.security import hash_password

router = APIRouter(tags=["admin"])
security = HTTPBasic()

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


def _require_admin(creds: HTTPBasicCredentials = Depends(security)) -> None:
    ok_user = secrets.compare_digest(creds.username, settings.admin_basic_user)
    ok_pass = secrets.compare_digest(creds.password, settings.admin_basic_password)
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )


@router.get("/admin", response_class=HTMLResponse)
def admin_index(
    request: Request,
    _: None = Depends(_require_admin),
    session: Session = Depends(get_session),
):
    users = list(session.exec(select(User).order_by(User.id.desc())))
    msg = request.query_params.get("msg")
    err = request.query_params.get("err")
    return templates.TemplateResponse(
        request=request,
        name="admin/index.html",
        context={"users": users, "memos_base_url": settings.memos_base_url, "msg": msg, "err": err},
    )


@router.post("/admin/users/create")
async def admin_create_user(
    request: Request,
    _: None = Depends(_require_admin),
    session: Session = Depends(get_session),
):
    form = await request.form()
    username = str(form.get("username") or "").strip()
    password = str(form.get("password") or "")
    password2 = str(form.get("password2") or "")

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

    existing = session.exec(select(User).where(User.username == username)).first()
    if existing:
        return _admin_redirect(err="用户名已存在")

    if settings.dev_bypass_memos:
        memos_user_id = 0
        memos_token = f"dev-{secrets.token_urlsafe(24)}"
    else:
        if not settings.memos_admin_token.strip():
            return _admin_redirect(err="未配置 MEMOS_ADMIN_TOKEN（或设置 DEV_BYPASS_MEMOS=true 用于本地调试）")
        client = MemosClient(
            base_url=settings.memos_base_url,
            admin_token=settings.memos_admin_token,
            timeout_seconds=settings.memos_request_timeout_seconds,
        )
        try:
            result = await client.create_user_and_token(
                create_user_endpoints=settings.create_user_endpoints_list(),
                create_token_endpoints=settings.create_token_endpoints_list(),
                username=username,
                password=password,
                allow_reset_existing_user_password=settings.memos_allow_reset_password_for_existing_user,
            )
            memos_user_id = result.memos_user_id
            memos_token = result.memos_token
        except MemosClientError as e:
            return _admin_redirect(err=f"Memos 对接失败：{e}")

    user = User(
        username=username,
        password_hash="",
        memos_id=memos_user_id,
        memos_token=memos_token,
        is_active=True,
    )
    try:
        user.password_hash = hash_password(password)
    except ValueError as e:
        return _admin_redirect(err=str(e))
    try:
        session.add(user)
        session.commit()
    except IntegrityError:
        session.rollback()
        return _admin_redirect(err="用户名已存在")

    return _admin_redirect(msg="创建成功")


@router.post("/admin/users/{user_id}/toggle-active")
def toggle_active(
    user_id: int,
    _: None = Depends(_require_admin),
    session: Session = Depends(get_session),
):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    user.is_active = not user.is_active
    session.add(user)
    session.commit()
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/users/{user_id}/delete")
def delete_user(
    user_id: int,
    _: None = Depends(_require_admin),
    session: Session = Depends(get_session),
):
    user = session.get(User, user_id)
    if not user:
        return _admin_redirect(err="用户不存在")
    session.delete(user)
    session.commit()
    return _admin_redirect(msg="已删除")


@router.post("/admin/users/{user_id}/reset-token")
async def reset_token(
    user_id: int,
    _: None = Depends(_require_admin),
    session: Session = Depends(get_session),
):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")

    if settings.dev_bypass_memos:
        user.memos_token = f"dev-{secrets.token_urlsafe(24)}"
    else:
        if not settings.memos_admin_token.strip():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="MEMOS_ADMIN_TOKEN is not set (or set DEV_BYPASS_MEMOS=true for local dev)",
            )
        if not user.memos_id:
            raise HTTPException(status_code=400, detail="user.memos_id is empty; cannot reset token")
        if not user.memos_token:
            raise HTTPException(status_code=400, detail="user.memos_token is empty; cannot reset token")
        client = MemosClient(
            base_url=settings.memos_base_url,
            admin_token=settings.memos_admin_token,
            timeout_seconds=settings.memos_request_timeout_seconds,
        )
        try:
            # 使用“现有用户 token”自助签发新 token（避免保存/回收用户明文密码）
            user.memos_token = await client.create_access_token_with_bearer(
                user_id=int(user.memos_id),
                bearer_token=user.memos_token,
                token_name=f"flow-reset-{user.username}",
            )
        except MemosClientError as e:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    session.add(user)
    session.commit()
    return RedirectResponse(url="/admin", status_code=303)
