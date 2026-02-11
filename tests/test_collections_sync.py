# pyright: reportArgumentType=false

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


def _find_by_id(items: list[object], entity_id: str) -> dict[str, object] | None:
    for it in items:
        d = cast(dict[str, object], it)
        if d.get("id") == entity_id:
            return d
    return None


def _find_rejected_by_entity_id(rejected: list[object], entity_id: str) -> dict[str, object] | None:
    for it in rejected:
        d = cast(dict[str, object], it)
        if d.get("entity_id") == entity_id:
            return d
    return None


@pytest.mark.anyio
async def test_v2_sync_collection_items_incremental_conflict_tombstone_and_revive(tmp_path: Path):
    old_db = settings.database_url
    try:
        settings.database_url = f"sqlite:///{tmp_path / 'test-v2-sync-collections.db'}"
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

        item_id = "col-item-folder-1"

        async with _make_async_client() as client:
            r = await client.post(
                "/api/v1/sync/push",
                headers={"Authorization": "Bearer tok-u1"},
                json={
                    "mutations": [
                        {
                            "resource": "collection_item",
                            "entity_id": item_id,
                            "op": "upsert",
                            "client_updated_at_ms": 1000,
                            "data": {"item_type": "folder", "name": "F1", "sort_order": 1},
                        }
                    ]
                },
            )
            assert r.status_code == 200
            push_body = cast(dict[str, object], r.json())
            applied = cast(list[object], push_body.get("applied"))
            assert any(cast(dict[str, object], a).get("entity_id") == item_id for a in applied)

            r2 = await client.get(
                "/api/v1/sync/pull?cursor=0&limit=200",
                headers={"Authorization": "Bearer tok-u1"},
            )
            assert r2.status_code == 200
            pull_body = cast(dict[str, object], r2.json())
            changes = cast(dict[str, object], pull_body.get("changes"))
            assert "collection_items" in changes
            collection_items = cast(list[object], changes.get("collection_items"))
            got = _find_by_id(collection_items, item_id)
            assert got is not None
            assert got.get("item_type") == "folder"
            assert got.get("name") == "F1"
            assert got.get("deleted_at") is None

            r3 = await client.post(
                "/api/v1/sync/push",
                headers={"Authorization": "Bearer tok-u1"},
                json={
                    "mutations": [
                        {
                            "resource": "collection_item",
                            "entity_id": item_id,
                            "op": "upsert",
                            "client_updated_at_ms": 10,
                            "data": {"item_type": "folder", "name": "STALE"},
                        }
                    ]
                },
            )
            assert r3.status_code == 200
            push2 = cast(dict[str, object], r3.json())
            rejected = cast(list[object], push2.get("rejected"))
            rej = _find_rejected_by_entity_id(rejected, item_id)
            assert rej is not None
            assert rej.get("reason") == "conflict"
            server = cast(dict[str, object], rej.get("server"))
            assert int(cast(int, server.get("client_updated_at_ms"))) == 1000

            r4 = await client.post(
                "/api/v1/sync/push",
                headers={"Authorization": "Bearer tok-u1"},
                json={
                    "mutations": [
                        {
                            "resource": "collection_item",
                            "entity_id": item_id,
                            "op": "delete",
                            "client_updated_at_ms": 2000,
                        }
                    ]
                },
            )
            assert r4.status_code == 200
            push3 = cast(dict[str, object], r4.json())
            applied3 = cast(list[object], push3.get("applied"))
            assert any(cast(dict[str, object], a).get("entity_id") == item_id for a in applied3)

            r5 = await client.get(
                "/api/v1/sync/pull?cursor=0&limit=200",
                headers={"Authorization": "Bearer tok-u1"},
            )
            assert r5.status_code == 200
            pull2 = cast(dict[str, object], r5.json())
            changes2 = cast(dict[str, object], pull2.get("changes"))
            assert "collection_items" in changes2
            collection_items2 = cast(list[object], changes2.get("collection_items"))
            got2 = _find_by_id(collection_items2, item_id)
            assert got2 is not None
            assert got2.get("deleted_at") is not None

            r6 = await client.post(
                "/api/v1/sync/push",
                headers={"Authorization": "Bearer tok-u1"},
                json={
                    "mutations": [
                        {
                            "resource": "collection_item",
                            "entity_id": item_id,
                            "op": "upsert",
                            "client_updated_at_ms": 3000,
                            "data": {"item_type": "folder", "name": "F1-REVIVED"},
                        }
                    ]
                },
            )
            assert r6.status_code == 200

            r7 = await client.get(
                "/api/v1/sync/pull?cursor=0&limit=200",
                headers={"Authorization": "Bearer tok-u1"},
            )
            assert r7.status_code == 200
            pull3 = cast(dict[str, object], r7.json())
            changes3 = cast(dict[str, object], pull3.get("changes"))
            assert "collection_items" in changes3
            collection_items3 = cast(list[object], changes3.get("collection_items"))
            got3 = _find_by_id(collection_items3, item_id)
            assert got3 is not None
            assert got3.get("deleted_at") is None
            assert got3.get("name") == "F1-REVIVED"
    finally:
        settings.database_url = old_db
