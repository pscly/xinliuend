"""Admin-editable site-wide settings backed by the `site_settings` table.

Values are stored as JSON strings keyed by a dotted name (e.g. `smtp.host`).
A small in-process cache (30s TTL, invalidated on write) avoids per-request
DB hits for hot settings like SMTP config.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.models import SiteSetting, utc_now


_CACHE_TTL_SECONDS = 30.0


class _Cache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> tuple[bool, Any]:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return False, None
            stamp, value = entry
            if (time.monotonic() - stamp) > _CACHE_TTL_SECONDS:
                self._entries.pop(key, None)
                return False, None
            return True, value

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            self._entries[key] = (time.monotonic(), value)

    def invalidate(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._entries.clear()
            else:
                self._entries.pop(key, None)


_cache = _Cache()


def _decode(raw: str | None) -> Any:
    if raw is None:
        return None
    if raw == "":
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


async def get_setting(session: AsyncSession, key: str) -> Any | None:
    hit, cached = _cache.get(key)
    if hit:
        return cached
    row = await session.get(SiteSetting, key)
    value = _decode(row.value_json) if row is not None else None
    _cache.put(key, value)
    return value


async def get_settings_by_prefix(
    session: AsyncSession, prefix: str
) -> dict[str, Any]:
    """Return all settings whose key starts with the given prefix (e.g. 'smtp.')."""

    rows = list(
        await session.exec(select(SiteSetting).where(SiteSetting.key.like(f"{prefix}%")))  # type: ignore[attr-defined]
    )
    out: dict[str, Any] = {}
    for row in rows:
        out[row.key] = _decode(row.value_json)
    return out


async def set_setting(
    session: AsyncSession,
    key: str,
    value: Any,
    *,
    updated_by: str | None = None,
) -> None:
    """Upsert a single setting and invalidate its cache entry."""

    payload = json.dumps(value, ensure_ascii=False) if value is not None else ""
    row = await session.get(SiteSetting, key)
    now = utc_now()
    if row is None:
        row = SiteSetting(
            key=key,
            value_json=payload,
            updated_at=now,
            updated_by=updated_by,
        )
        session.add(row)
    else:
        row.value_json = payload
        row.updated_at = now
        row.updated_by = updated_by
        session.add(row)
    await session.commit()
    _cache.invalidate(key)


async def set_many(
    session: AsyncSession,
    items: dict[str, Any],
    *,
    updated_by: str | None = None,
) -> None:
    """Upsert multiple settings in a single transaction; invalidate them all."""

    now = utc_now()
    for key, value in items.items():
        payload = json.dumps(value, ensure_ascii=False) if value is not None else ""
        row = await session.get(SiteSetting, key)
        if row is None:
            row = SiteSetting(
                key=key,
                value_json=payload,
                updated_at=now,
                updated_by=updated_by,
            )
            session.add(row)
        else:
            row.value_json = payload
            row.updated_at = now
            row.updated_by = updated_by
            session.add(row)
    await session.commit()
    for key in items.keys():
        _cache.invalidate(key)


def invalidate_cache(key: str | None = None) -> None:
    """Public helper for tests / migrations to flush cached values."""

    _cache.invalidate(key)
