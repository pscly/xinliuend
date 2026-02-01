from __future__ import annotations

from pathlib import Path
from typing import cast

import httpx
import pytest
from alembic import command
from alembic.config import Config

from flow_backend.config import settings
from flow_backend.db import reset_engine_cache, session_scope
from flow_backend.main import app  # pyright: ignore[reportMissingTypeStubs]
from flow_backend.models import User


def _make_async_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _alembic_upgrade_head() -> None:
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")


@pytest.mark.anyio
async def test_v2_sync_notes_push_pull_and_conflict(tmp_path: Path):
    old_db = settings.database_url
    try:
        settings.database_url = f"sqlite:///{tmp_path / 'test-v2-sync.db'}"
        reset_engine_cache()
        _alembic_upgrade_head()

        async with session_scope() as session:
            session.add(
                User(
                    username="u1",
                    password_hash="x",
                    memos_id=None,
                    memos_token="tok-u1",
                    is_active=True,
                )
            )
            await session.commit()

        async with _make_async_client() as client:
            # Create note via sync push.
            r = await client.post(
                "/api/v2/sync/push",
                headers={"Authorization": "Bearer tok-u1"},
                json={
                    "mutations": [
                        {
                            "resource": "note",
                            "entity_id": "note-1",
                            "op": "upsert",
                            "client_updated_at_ms": 1000,
                            "data": {"title": "t", "body_md": "hello", "tags": ["work"]},
                        }
                    ]
                },
            )
            assert r.status_code == 200
            body = cast(dict[str, object], r.json())
            applied = cast(list[object], body.get("applied"))
            assert any(cast(dict[str, object], a).get("entity_id") == "note-1" for a in applied)
            cursor = int(cast(int, body.get("cursor")))
            assert cursor >= 1

            # Pull should include the note.
            r2 = await client.get(
                "/api/v2/sync/pull?cursor=0&limit=200",
                headers={"Authorization": "Bearer tok-u1"},
            )
            assert r2.status_code == 200
            pull_body = cast(dict[str, object], r2.json())
            changes = cast(dict[str, object], pull_body.get("changes"))
            notes = cast(list[object], changes.get("notes"))
            assert any(cast(dict[str, object], n).get("id") == "note-1" for n in notes)

            # Stale update rejected with conflict.
            r3 = await client.post(
                "/api/v2/sync/push",
                headers={"Authorization": "Bearer tok-u1"},
                json={
                    "mutations": [
                        {
                            "resource": "note",
                            "entity_id": "note-1",
                            "op": "upsert",
                            "client_updated_at_ms": 10,
                            "data": {"title": "stale"},
                        }
                    ]
                },
            )
            assert r3.status_code == 200
            push2 = cast(dict[str, object], r3.json())
            rejected = cast(list[object], push2.get("rejected"))
            assert rejected
            rej0 = cast(dict[str, object], rejected[0])
            assert rej0.get("reason") == "conflict"
            server = cast(dict[str, object], rej0.get("server"))
            assert int(cast(int, server.get("client_updated_at_ms"))) == 1000

            # Delete non-existent note is idempotent.
            r4 = await client.post(
                "/api/v2/sync/push",
                headers={"Authorization": "Bearer tok-u1"},
                json={
                    "mutations": [
                        {
                            "resource": "note",
                            "entity_id": "note-does-not-exist",
                            "op": "delete",
                            "client_updated_at_ms": 100,
                        }
                    ]
                },
            )
            assert r4.status_code == 200
            push3 = cast(dict[str, object], r4.json())
            applied3 = cast(list[object], push3.get("applied"))
            assert any(
                cast(dict[str, object], a).get("entity_id") == "note-does-not-exist"
                for a in applied3
            )
    finally:
        settings.database_url = old_db
