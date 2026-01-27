from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.config import settings
from flow_backend.models import SyncEvent, utc_now


def now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def clamp_client_updated_at_ms(value: int | None) -> int:
    if not value or value < 0:
        return 0
    server_now = now_ms()
    max_ahead = settings.sync_max_client_clock_skew_seconds * 1000
    if value > server_now + max_ahead:
        return server_now + max_ahead
    return value


def record_sync_event(
    session: AsyncSession, user_id: int, resource: str, entity_id: str, action: str
) -> None:
    session.add(
        SyncEvent(
            user_id=user_id,
            resource=resource,
            entity_id=entity_id,
            action=action,
            created_at=utc_now(),
        )
    )
