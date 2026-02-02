# pyright: ignore
# basedpyright: ignore
# pyright: reportAttributeAccessIssue=false

from __future__ import annotations

import hashlib
import logging

from fastapi import HTTPException, status
import sqlalchemy as sa
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.config import settings
from flow_backend.db import session_scope
from flow_backend.models import utc_now
from flow_backend.sync_utils import now_ms


logger = logging.getLogger(__name__)


_last_cleanup_ms = 0


async def _maybe_cleanup(*, session: AsyncSession, now_ms_value: int) -> None:
    # Best-effort cleanup to avoid unbounded table growth.
    global _last_cleanup_ms

    interval_s = int(settings.rate_limit_cleanup_interval_seconds)
    retention_s = int(settings.rate_limit_retention_seconds)
    if interval_s <= 0 or retention_s <= 0:
        return

    interval_ms = interval_s * 1000
    if _last_cleanup_ms and now_ms_value - _last_cleanup_ms < interval_ms:
        return
    _last_cleanup_ms = now_ms_value

    cutoff_ms = now_ms_value - (retention_s * 1000)
    if cutoff_ms <= 0:
        return

    table = SQLModel.metadata.tables["rate_limit_counters"]
    await session.exec(sa.delete(table).where(table.c.window_start_ms < int(cutoff_ms)))


def _window_start_ms(*, now_ms_value: int, window_seconds: int) -> int:
    window_ms = int(window_seconds) * 1000
    if window_ms <= 0:
        return now_ms_value
    return (now_ms_value // window_ms) * window_ms


def build_ip_key(ip: str | None) -> str:
    v = (ip or "").strip() or "unknown"
    # Keep keys small (they are indexed).
    return f"ip:{v}"[:128]


def build_ip_username_key(*, ip: str | None, username: str | None) -> str:
    ip_v = (ip or "").strip() or "unknown"
    user_v = (username or "").strip().lower()
    user_hash = hashlib.sha256(user_v.encode("utf-8")).hexdigest()[:16]
    return f"ip:{ip_v}:u:{user_hash}"[:128]


def _is_sqlite() -> bool:
    return settings.database_url.lower().startswith("sqlite")


def _is_postgres() -> bool:
    v = settings.database_url.lower()
    return v.startswith("postgresql") or v.startswith("postgres")


async def _hit_counter(
    *,
    session: AsyncSession,
    scope: str,
    key: str,
    window_start_ms: int,
) -> int:
    table = SQLModel.metadata.tables["rate_limit_counters"]
    now = utc_now()

    values: dict[str, object] = {
        "scope": scope,
        "key": key,
        "window_start_ms": int(window_start_ms),
        "count": 1,
        "created_at": now,
        "updated_at": now,
    }

    if _is_sqlite():
        from sqlalchemy.dialects.sqlite import insert as dialect_insert

        stmt = dialect_insert(table).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["scope", "key", "window_start_ms"],
            set_={
                "count": table.c.count + 1,
                "updated_at": now,
            },
        )
        stmt = stmt.returning(table.c.count)
        row = (await session.exec(stmt)).first()
        return 0 if row is None else int(row[0])
    elif _is_postgres():
        from sqlalchemy.dialects.postgresql import insert as dialect_insert

        stmt = dialect_insert(table).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["scope", "key", "window_start_ms"],
            set_={
                "count": table.c.count + 1,
                "updated_at": now,
            },
        )
        stmt = stmt.returning(table.c.count)
        row = (await session.exec(stmt)).first()
        return 0 if row is None else int(row[0])
    else:
        # Best-effort fallback for other DBs.
        try:
            await session.exec(sa.insert(table).values(**values))
        except Exception:
            await session.rollback()
            await session.exec(
                sa.update(table)
                .where(table.c.scope == scope)
                .where(table.c.key == key)
                .where(table.c.window_start_ms == int(window_start_ms))
                .values(count=table.c.count + 1, updated_at=now)
            )
        # If we can't read back the exact counter value, return a safe-ish lower bound.
        return 1


async def enforce_rate_limit(*, scope: str, key: str, limit: int, window_seconds: int) -> None:
    """Increment the limiter and raise 429 when over limit.

    This is best-effort: if limit/window is misconfigured (<=0), it is disabled.
    """

    limit_i = int(limit)
    window_s = int(window_seconds)
    if limit_i <= 0 or window_s <= 0:
        return

    now_ms_value = now_ms()
    window_ms = window_s * 1000
    start_ms = _window_start_ms(now_ms_value=now_ms_value, window_seconds=window_s)

    async with session_scope() as session:
        try:
            count = await _hit_counter(
                session=session, scope=scope, key=key, window_start_ms=start_ms
            )
            await _maybe_cleanup(session=session, now_ms_value=now_ms_value)
            await session.commit()
        except Exception:
            # Best-effort: rate limiting must never break primary request flows.
            logger.warning("rate limit check failed scope=%s", scope, exc_info=True)
            return

    if count <= limit_i:
        return

    retry_after_s = max(1, int((start_ms + window_ms - now_ms_value + 999) // 1000))
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="too many requests",
        headers={"Retry-After": str(retry_after_s)},
    )
