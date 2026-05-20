from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.config import settings
from flow_backend.memos_client import MemosClient, MemosClientError
from flow_backend.models import User


@dataclass(frozen=True)
class ValidatedMemosCredential:
    token: str
    memos_user_id: int | None
    memos_user_name: str
    memos_username: str


def normalize_memos_token(value: str | None) -> str | None:
    token = (value or "").strip()
    return token or None


def token_preview(token: str | None) -> str | None:
    token = normalize_memos_token(token)
    if token is None:
        return None
    if len(token) <= 6:
        return f"{token[:2]}…{token[-1:]}"
    if len(token) <= 14:
        return f"{token[:4]}…{token[-2:]}"
    return f"{token[:8]}…{token[-6:]}"


def can_auto_issue_memos_token() -> bool:
    return _memos_base_url_configured()


def _memos_base_url_configured() -> bool:
    base_url = (settings.memos_base_url or "").strip()
    return bool(base_url) and base_url != "https://memos.example.com"


def _ensure_memos_base_url_configured() -> None:
    if not _memos_base_url_configured():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="MEMOS_BASE_URL is not configured",
        )


def _get_str(data: dict[str, Any], key: str) -> str | None:
    v = data.get(key)
    if isinstance(v, str) and v.strip():
        return v.strip()
    return None


def _get_int(data: dict[str, Any], key: str) -> int | None:
    v = data.get(key)
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.isdigit():
        return int(v)
    return None


def _extract_validated_info(info: dict[str, Any]) -> tuple[str, int | None, str]:
    username = _get_str(info, "username")
    user_id = _get_int(info, "user_id")
    user_name = _get_str(info, "user_name") or _get_str(info, "name")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Memos Token 校验成功，但无法解析 Memos 用户名",
        )
    if not user_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Memos Token 校验成功，但无法解析 Memos 用户资源名",
        )
    return username, user_id, user_name


def _build_memos_client() -> MemosClient:
    _ensure_memos_base_url_configured()
    return MemosClient(
        base_url=settings.memos_base_url,
        admin_token=settings.memos_admin_token,
        timeout_seconds=settings.memos_request_timeout_seconds,
        trust_env=settings.memos_http_trust_env,
    )


async def validate_memos_token_for_user(
    *,
    session: AsyncSession,
    user: User,
    token: str,
    memos_user_id: int | None = None,
    allow_username_mismatch: bool = False,
) -> ValidatedMemosCredential:
    clean_token = normalize_memos_token(token)
    if clean_token is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="memos_token is required"
        )

    user_id = user.id
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="user id missing"
        )

    existing = (
        await session.exec(
            select(User).where((User.memos_token == clean_token) & (User.id != int(user_id)))
        )
    ).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Token 已被其它用户占用")

    client = _build_memos_client()
    try:
        info = await client.get_current_user_with_bearer(clean_token)
    except MemosClientError as exc:
        message = str(exc)
        status_code = status.HTTP_400_BAD_REQUEST
        if "401" in message or "403" in message:
            detail = "Memos Token 无效或无权访问当前 Memos 用户"
        else:
            status_code = status.HTTP_502_BAD_GATEWAY
            detail = "Memos 服务不可用，暂时无法校验 Token"
        raise HTTPException(status_code=status_code, detail=detail) from exc

    resolved_username, resolved_memos_user_id, resolved_memos_user_name = _extract_validated_info(info)
    if (not allow_username_mismatch) and resolved_username != user.username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Memos username mismatch: expected {user.username}, got {resolved_username}",
        )

    if (
        memos_user_id is not None
        and resolved_memos_user_id is not None
        and int(memos_user_id) != resolved_memos_user_id
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="memos_user_id does not match Memos Token owner",
        )

    return ValidatedMemosCredential(
        token=clean_token,
        memos_user_id=resolved_memos_user_id,
        memos_user_name=resolved_memos_user_name,
        memos_username=resolved_username,
    )


async def force_save_memos_credential_unchecked(
    *,
    session: AsyncSession,
    user: User,
    token: str,
    memos_user_id: int | None,
) -> ValidatedMemosCredential:
    """Admin escape hatch: write a memos token to the user WITHOUT calling Memos."""

    clean_token = normalize_memos_token(token)
    if clean_token is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="memos_token is required",
        )
    user_id = user.id
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="user id missing"
        )

    existing = (
        await session.exec(
            select(User).where((User.memos_token == clean_token) & (User.id != int(user_id)))
        )
    ).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Token 已被其它用户占用")

    resolved_id = int(memos_user_id) if memos_user_id is not None and int(memos_user_id) >= 0 else None
    resource_name = user.memos_user_name or (
        f"users/{resolved_id}" if resolved_id is not None else f"users/{user.username}"
    )
    credential = ValidatedMemosCredential(
        token=clean_token,
        memos_user_id=resolved_id,
        memos_user_name=resource_name,
        memos_username=user.username,
    )
    await save_memos_credential(session=session, user_id=int(user_id), credential=credential)
    return credential


async def save_memos_credential(
    *,
    session: AsyncSession,
    user_id: int,
    credential: ValidatedMemosCredential,
) -> User:
    user_row = await session.get(User, int(user_id))
    if user_row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    user_row.memos_token = credential.token
    user_row.memos_id = credential.memos_user_id
    user_row.memos_user_name = credential.memos_user_name
    session.add(user_row)
    try:
        await session.commit()
        await session.refresh(user_row)
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Token 已被其它用户占用"
        ) from exc
    return user_row


async def clear_memos_credential(*, session: AsyncSession, user_id: int) -> User:
    user_row = await session.get(User, int(user_id))
    if user_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    # 只清 token，保留 memos_id / memos_user_name 作为身份锚点，避免后续改密/修复链路失去目标用户。
    # 对历史只有 memos_id 的老数据，顺手回填资源名，后续新版 Memos 路径可直接复用。
    if not user_row.memos_user_name and user_row.memos_id and int(user_row.memos_id) > 0:
        user_row.memos_user_name = f"users/{int(user_row.memos_id)}"
    user_row.memos_token = None
    session.add(user_row)
    await session.commit()
    await session.refresh(user_row)
    return user_row


async def issue_memos_personal_access_token(
    *,
    user: User,
    app_password: str,
) -> ValidatedMemosCredential:
    client = _build_memos_client()
    token_name = f"flow-{user.username}-self-service"

    try:
        sign_in = await client.sign_in_with_password(
            username=user.username, app_password=app_password
        )
        memos_username, memos_user_id, memos_user_name = _extract_validated_info(sign_in)
        access_token = _get_str(sign_in, "access_token")
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Memos 登录成功，但未返回 access token",
            )
        if memos_username != user.username:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Memos username mismatch: expected {user.username}, got {memos_username}",
            )
        pat = await client.create_personal_access_token_with_bearer(
            user_name=memos_user_name,
            bearer_token=access_token,
            description=token_name,
            expires_in_days=0,
        )
        return ValidatedMemosCredential(
            token=pat,
            memos_user_id=memos_user_id,
            memos_user_name=memos_user_name,
            memos_username=memos_username,
        )
    except HTTPException:
        raise
    except MemosClientError as primary_exc:
        if (
            hasattr(client, "create_access_token_as_user")
            and (
                (user.memos_user_name and user.memos_user_name.startswith("users/"))
                or (user.memos_id and int(user.memos_id) > 0)
            )
        ):
            try:
                legacy_user_name = user.memos_user_name or f"users/{int(user.memos_id)}"
                legacy_pat = await client.create_access_token_as_user(
                    user_name=legacy_user_name,
                    username=user.username,
                    password=app_password,
                    token_name=token_name,
                )
                return ValidatedMemosCredential(
                    token=legacy_pat,
                    memos_user_id=int(user.memos_id) if user.memos_id else None,
                    memos_user_name=legacy_user_name,
                    memos_username=user.username,
                )
            except MemosClientError:
                pass
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Memos 服务不可用，无法自动签发 Token",
        ) from primary_exc
