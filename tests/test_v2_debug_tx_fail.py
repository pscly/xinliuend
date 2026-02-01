from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlmodel import select

from flow_backend.config import settings
from flow_backend.db import init_db, reset_engine_cache, session_scope
from flow_backend.main import app
from flow_backend.models import User, UserSetting
from flow_backend.security import hash_password


def _make_async_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.anyio
async def test_v2_debug_tx_fail_rolls_back(tmp_path: Path) -> None:
    settings.database_url = f"sqlite:///{tmp_path / 'test-v2-debug-tx-fail.db'}"
    reset_engine_cache()
    await init_db()

    async with session_scope() as session:
        user = User(
            username="u_tx_fail",
            password_hash=hash_password("pass1234"),
            memos_id=10,
            memos_token="tok-tx-fail",
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_db_id = user.id
        assert user_db_id is not None

    user_id = int(user_db_id)

    key = f"tx-fail-{uuid4()}"
    async with _make_async_client() as client:
        r = await client.post(
            "/api/v2/debug/tx-fail",
            json={"key": key},
            headers={"Authorization": "Bearer tok-tx-fail"},
        )
        assert 500 <= r.status_code < 600

    async with session_scope() as session:
        row = (
            await session.exec(
                select(UserSetting)
                .where(UserSetting.user_id == user_id)
                .where(UserSetting.key == key)
            )
        ).first()
        assert row is None
