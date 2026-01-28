from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.db import get_session
from flow_backend.deps import get_current_user
from flow_backend.models import User, UserSetting, utc_now
from flow_backend.schemas_settings import SettingDeleteRequest, SettingUpsertRequest
from flow_backend.sync_utils import clamp_client_updated_at_ms, now_ms, record_sync_event

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
async def list_settings(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    settings_rows = list(
        (
            await session.exec(
                select(UserSetting)
                .where(UserSetting.user_id == user.id)
                .where(UserSetting.deleted_at.is_(None))
                .order_by(UserSetting.key.asc())
            )
        )
    )
    data = [
        {
            "key": row.key,
            "value_json": row.value_json,
            "client_updated_at_ms": row.client_updated_at_ms,
            "updated_at": row.updated_at,
        }
        for row in settings_rows
    ]
    return {"code": 200, "data": {"items": data}}


@router.put("/{key}")
async def upsert_setting(
    key: str,
    payload: SettingUpsertRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not key.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="key is empty")
    if len(key) > 128:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="key too long")

    incoming_ms = clamp_client_updated_at_ms(payload.client_updated_at_ms) or now_ms()
    row = (
        await session.exec(
            select(UserSetting).where(UserSetting.user_id == user.id).where(UserSetting.key == key)
        )
    ).first()

    if row and incoming_ms < row.client_updated_at_ms:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="conflict (stale update)")

    if not row:
        row = UserSetting(user_id=int(user.id), key=key, value_json={}, client_updated_at_ms=0)

    row.value_json = payload.value_json
    row.client_updated_at_ms = incoming_ms
    row.updated_at = utc_now()
    row.deleted_at = None

    session.add(row)
    record_sync_event(
        session, user_id=int(user.id), resource="user_setting", entity_id=key, action="upsert"
    )
    await session.commit()
    await session.refresh(row)

    return {
        "code": 200,
        "data": {
            "key": row.key,
            "value_json": row.value_json,
            "client_updated_at_ms": row.client_updated_at_ms,
            "updated_at": row.updated_at,
            "deleted_at": row.deleted_at,
        },
    }


@router.delete("/{key}")
async def delete_setting(
    key: str,
    payload: SettingDeleteRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not key.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="key is empty")

    incoming_ms = clamp_client_updated_at_ms(payload.client_updated_at_ms) or now_ms()
    row = (
        await session.exec(
            select(UserSetting).where(UserSetting.user_id == user.id).where(UserSetting.key == key)
        )
    ).first()

    if row and incoming_ms < row.client_updated_at_ms:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="conflict (stale delete)")

    if not row:
        row = UserSetting(user_id=int(user.id), key=key, value_json={}, client_updated_at_ms=0)

    row.client_updated_at_ms = incoming_ms
    row.updated_at = utc_now()
    row.deleted_at = utc_now()

    session.add(row)
    record_sync_event(
        session, user_id=int(user.id), resource="user_setting", entity_id=key, action="delete"
    )
    await session.commit()

    return {"code": 200, "data": {"ok": True}}
