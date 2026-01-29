from __future__ import annotations

import logging
from datetime import datetime

from fastapi import Request
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.config import settings
from flow_backend.models import UserDevice, UserDeviceIP, utc_now

logger = logging.getLogger(__name__)


def _header_first(request: Request, names: list[str]) -> str | None:
    for n in names:
        v = request.headers.get(n)
        if v and v.strip():
            return v.strip()
    return None


def extract_device_id_name(request: Request) -> tuple[str | None, str | None]:
    # Accept a couple of common variants to reduce coordination friction.
    device_id = _header_first(request, ["X-Flow-Device-Id", "X-Device-Id"])
    device_name = _header_first(request, ["X-Flow-Device-Name", "X-Device-Name"])
    return device_id, device_name


def extract_client_ip(request: Request) -> str | None:
    if settings.trust_x_forwarded_for:
        raw = request.headers.get("x-forwarded-for")
        if raw:
            # Take the left-most (original) client IP.
            first = raw.split(",")[0].strip()
            if first:
                return first
    if request.client:
        return request.client.host
    return None


async def record_device_activity(session: AsyncSession, user_id: int, request: Request) -> None:
    device_id, device_name = extract_device_id_name(request)
    if not device_id:
        return

    now: datetime = utc_now()
    ip = extract_client_ip(request)
    ua = request.headers.get("user-agent")

    device = (
        await session.exec(
            select(UserDevice)
            .where(UserDevice.user_id == user_id)
            .where(UserDevice.device_id == device_id)
        )
    ).first()

    if not device:
        device = UserDevice(
            user_id=user_id,
            device_id=device_id,
            device_name=device_name,
            first_seen=now,
            last_seen=now,
            last_ip=ip,
            last_user_agent=ua,
            created_at=now,
            updated_at=now,
        )
        session.add(device)
    else:
        # Don't overwrite with empty values.
        if device_name:
            device.device_name = device_name
        device.last_seen = now
        device.updated_at = now
        if ip:
            device.last_ip = ip
        if ua:
            device.last_user_agent = ua
        session.add(device)

    if ip:
        ip_row = (
            await session.exec(
                select(UserDeviceIP)
                .where(UserDeviceIP.user_id == user_id)
                .where(UserDeviceIP.device_id == device_id)
                .where(UserDeviceIP.ip == ip)
            )
        ).first()
        if not ip_row:
            ip_row = UserDeviceIP(
                user_id=user_id,
                device_id=device_id,
                ip=ip,
                first_seen=now,
                last_seen=now,
                created_at=now,
                updated_at=now,
            )
        else:
            ip_row.last_seen = now
            ip_row.updated_at = now
        session.add(ip_row)

    try:
        await session.commit()
    except Exception:
        await session.rollback()
        logger.warning("record_device_activity failed", exc_info=True)
