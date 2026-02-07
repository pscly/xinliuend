from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Annotated, Final

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.config import settings
from flow_backend.db import get_session
from flow_backend.deps import get_current_user
from flow_backend.integrations.memos_notes_api import (
    HttpxMemosNotesAPI,
    MemosNotesAPI,
    MemosNotesError,
    memo_id_from_remote_id,
)
from flow_backend.models import User
from flow_backend.models_notes import NoteRemote
from flow_backend.schemas_memos_migration import (
    MemosMigrationResponse,
    MemosMigrationSummary,
    MemosNoteItem,
    MemosNoteListResponse,
)
from flow_backend.services import memos_sync_service

router = APIRouter(prefix="/memos", tags=["memos"])

_MIGRATION_LOCK_TIMEOUT_SECONDS: Final[float] = 0.2
_USER_LOCKS: dict[int, asyncio.Lock] = {}
_MEMO_CONTENT_MAX_LEN: Final[int] = 20000
_MEMO_TITLE_MAX_LEN: Final[int] = 500


def _lock_for_user(user_id: int) -> asyncio.Lock:
    lock = _USER_LOCKS.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _USER_LOCKS[user_id] = lock
    return lock


def _memo_title_from_content(content: str) -> str:
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        return line[:_MEMO_TITLE_MAX_LEN]
    return ""


def _updated_at_from_ms(updated_at_ms: int | None) -> datetime | None:
    if updated_at_ms is None:
        return None
    try:
        return datetime.fromtimestamp(updated_at_ms / 1000.0, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _remote_lookup_keys(remote_id: str) -> list[str]:
    keys = {remote_id.strip()}
    try:
        memo_id = memo_id_from_remote_id(remote_id)
    except MemosNotesError:
        memo_id = ""
    if memo_id:
        keys.add(memo_id)
        keys.add(f"memos/{memo_id}")
    return [k for k in keys if k]


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


@router.get("/notes", response_model=MemosNoteListResponse)
async def list_memos_notes(
    limit: Annotated[int, Query(ge=1, le=500)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    include_deleted: Annotated[bool, Query()] = False,
    user: User = Depends(get_current_user),
    memos_api: MemosNotesAPI = Depends(get_memos_notes_api),
    session: AsyncSession = Depends(get_session),
) -> MemosNoteListResponse:
    user_id = user.id
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="用户缺少 id（服务器内部错误）",
        )

    try:
        memos = await memos_api.list_memos()
    except MemosNotesError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Memos 接口调用失败：{e}",
        )

    if not include_deleted:
        memos = [m for m in memos if not m.deleted]

    memos.sort(
        key=lambda m: (
            int(m.updated_at_ms if m.updated_at_ms is not None else 0),
            m.remote_id,
        ),
        reverse=True,
    )

    total = len(memos)
    page_items = memos[offset : offset + limit]

    remote_rows = list(
        (
            await session.exec(
                select(NoteRemote)
                .where(NoteRemote.user_id == int(user_id))
                .where(NoteRemote.provider == "memos")
                .where(NoteRemote.deleted_at.is_(None))
            )
        )
    )
    linked_by_remote: dict[str, str] = {}
    for row in remote_rows:
        if not row.note_id:
            continue
        for key in _remote_lookup_keys(row.remote_id):
            linked_by_remote.setdefault(key, row.note_id)

    warnings: list[str] = []
    truncated_count = 0
    items: list[MemosNoteItem] = []
    for memo in page_items:
        body_md = memo.content
        if len(body_md) > _MEMO_CONTENT_MAX_LEN:
            body_md = body_md[:_MEMO_CONTENT_MAX_LEN]
            truncated_count += 1

        linked_local_note_id = None
        for key in _remote_lookup_keys(memo.remote_id):
            local_note_id = linked_by_remote.get(key)
            if local_note_id:
                linked_local_note_id = local_note_id
                break

        items.append(
            MemosNoteItem(
                remote_id=memo.remote_id,
                title=_memo_title_from_content(body_md),
                body_md=body_md,
                updated_at=_updated_at_from_ms(memo.updated_at_ms),
                deleted=memo.deleted,
                source="memos",
                linked_local_note_id=linked_local_note_id,
            )
        )

    if truncated_count > 0:
        warnings.append(f"{truncated_count} 条 Memos 内容过长，已截断为 {_MEMO_CONTENT_MAX_LEN} 字符。")

    return MemosNoteListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        warnings=warnings,
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
