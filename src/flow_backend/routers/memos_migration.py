from __future__ import annotations

import asyncio
from typing import Final

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.config import settings
from flow_backend.db import get_session
from flow_backend.deps import get_current_user
from flow_backend.integrations.memos_notes_api import (
    HttpxMemosNotesAPI,
    MemosNotesAPI,
    MemosNotesError,
)
from flow_backend.models import User
from flow_backend.schemas_memos_migration import MemosMigrationResponse, MemosMigrationSummary
from flow_backend.services import memos_sync_service

router = APIRouter(prefix="/memos", tags=["memos"])

_MIGRATION_LOCK_TIMEOUT_SECONDS: Final[float] = 0.2
_USER_LOCKS: dict[int, asyncio.Lock] = {}


def _lock_for_user(user_id: int) -> asyncio.Lock:
    lock = _USER_LOCKS.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _USER_LOCKS[user_id] = lock
    return lock


async def get_memos_notes_api(user: User = Depends(get_current_user)) -> MemosNotesAPI:
    if not user.memos_token or not user.memos_token.strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="当前账号未绑定 Memos Token，请联系管理员处理。",
        )

    base_url = settings.memos_base_url.strip()
    if not base_url or base_url == "https://memos.example.com":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="服务端未配置 MEMOS_BASE_URL，无法连接 Memos。",
        )

    return HttpxMemosNotesAPI(
        base_url=base_url,
        bearer_token=user.memos_token,
        timeout_seconds=settings.memos_request_timeout_seconds,
        list_endpoints=settings.note_list_endpoints_list(),
        upsert_endpoints=settings.note_upsert_endpoints_list(),
        delete_endpoints=settings.note_delete_endpoints_list(),
    )


@router.post("/migration/preview", response_model=MemosMigrationResponse)
async def preview_migration(
    user: User = Depends(get_current_user),
    memos_api: MemosNotesAPI = Depends(get_memos_notes_api),
    session: AsyncSession = Depends(get_session),
) -> MemosMigrationResponse:
    user_id = user.id
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="用户缺少 id（服务器内部错误）",
        )

    lock = _lock_for_user(int(user_id))
    try:
        await asyncio.wait_for(lock.acquire(), timeout=_MIGRATION_LOCK_TIMEOUT_SECONDS)
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="迁移任务正在执行中，请稍后再试。",
        )

    try:
        summary = await memos_sync_service.plan_pull_user_notes(
            session=session,
            user_id=int(user_id),
            memos_api=memos_api,
        )
    except MemosNotesError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Memos 接口调用失败：{e}",
        )
    finally:
        lock.release()

    return MemosMigrationResponse(
        ok=True,
        kind="preview",
        summary=MemosMigrationSummary(
            remote_total=summary.remote_total,
            created_local=summary.created_local,
            updated_local_from_remote=summary.updated_local_from_remote,
            deleted_local_from_remote=summary.deleted_local_from_remote,
            conflicts=summary.conflicts,
        ),
        memos_base_url=settings.memos_base_url,
    )


@router.post("/migration/apply", response_model=MemosMigrationResponse)
async def apply_migration(
    user: User = Depends(get_current_user),
    memos_api: MemosNotesAPI = Depends(get_memos_notes_api),
    session: AsyncSession = Depends(get_session),
) -> MemosMigrationResponse:
    user_id = user.id
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="用户缺少 id（服务器内部错误）",
        )

    lock = _lock_for_user(int(user_id))
    try:
        await asyncio.wait_for(lock.acquire(), timeout=_MIGRATION_LOCK_TIMEOUT_SECONDS)
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="迁移任务正在执行中，请稍后再试。",
        )

    try:
        summary = await memos_sync_service.apply_pull_user_notes(
            session=session,
            user_id=int(user_id),
            memos_api=memos_api,
        )
    except MemosNotesError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Memos 接口调用失败：{e}",
        )
    finally:
        lock.release()

    return MemosMigrationResponse(
        ok=True,
        kind="apply",
        summary=MemosMigrationSummary(
            remote_total=summary.remote_total,
            created_local=summary.created_local,
            updated_local_from_remote=summary.updated_local_from_remote,
            deleted_local_from_remote=summary.deleted_local_from_remote,
            conflicts=summary.conflicts,
        ),
        memos_base_url=settings.memos_base_url,
    )
