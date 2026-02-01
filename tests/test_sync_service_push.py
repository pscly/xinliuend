from __future__ import annotations

from pathlib import Path

import pytest
from sqlmodel import select

from flow_backend.config import settings
from flow_backend.db import init_db, reset_engine_cache, session_scope
from flow_backend.models import User, UserSetting
from flow_backend.schemas_sync import SyncMutation, SyncPushRequest
from flow_backend.services import sync_service


@pytest.mark.anyio
async def test_sync_service_push_persists_user_setting(tmp_path: Path) -> None:
    # Use per-test sqlite DB to keep the test isolated and deterministic.
    settings.database_url = f"sqlite:///{tmp_path / 'sync_push.db'}"
    reset_engine_cache()
    await init_db()

    async with session_scope() as session:
        user = User(
            username="u_sync_push",
            password_hash="not-a-real-hash",
            memos_id=1,
            memos_token="tok-sync-push",
            is_active=True,
        )
        session.add(user)
        await session.commit()
        assert user.id is not None
        user_id = int(user.id)

    req = SyncPushRequest(
        mutations=[
            SyncMutation(
                resource="user_setting",
                op="upsert",
                entity_id="theme",
                client_updated_at_ms=1000,
                data={"value_json": {"dark": True}},
            )
        ]
    )

    async with session_scope() as session:
        result = await sync_service.push(session=session, user=user, req=req)

    assert set(result.keys()) == {"cursor", "applied", "rejected"}
    assert isinstance(result["cursor"], int)
    assert result["cursor"] >= 1
    assert result["applied"] == [{"resource": "user_setting", "entity_id": "theme"}]
    assert result["rejected"] == []

    async with session_scope() as session:
        row = (
            await session.exec(
                select(UserSetting)
                .where(UserSetting.user_id == user_id)
                .where(UserSetting.key == "theme")
            )
        ).first()
        assert row is not None
        assert row.deleted_at is None
        assert row.client_updated_at_ms == 1000
        assert row.value_json == {"dark": True}
