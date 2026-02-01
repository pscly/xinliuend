from __future__ import annotations

from pathlib import Path
from typing import cast

import httpx
import pytest

from flow_backend.config import settings
from flow_backend.db import init_db, reset_engine_cache, session_scope
from flow_backend.main import app  # pyright: ignore[reportMissingTypeStubs]
from flow_backend.models import User


def _make_async_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.anyio
async def test_v2_todo_items_crud_and_sync_events(tmp_path: Path):
    old_db = settings.database_url
    old_tzid = settings.default_tzid
    try:
        settings.database_url = f"sqlite:///{tmp_path / 'test-v2-todo-crud.db'}"
        settings.default_tzid = "UTC"
        reset_engine_cache()
        await init_db()

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

        headers = {"Authorization": "Bearer tok-u1"}
        async with _make_async_client() as client:
            # Create list via v1 (v2 has items only for now).
            r = await client.post(
                "/api/v1/todo/lists",
                json={
                    "name": "inbox",
                    "color": None,
                    "sort_order": 1,
                    "archived": False,
                    "client_updated_at_ms": 1000,
                },
                headers=headers,
            )
            assert r.status_code == 200
            list_id = r.json()["data"]["id"]

            # Create item (tzid falls back to settings.default_tzid).
            r2 = await client.post(
                "/api/v2/todo/items",
                json={
                    "list_id": list_id,
                    "title": "喝水",
                    "tags": ["health"],
                    "client_updated_at_ms": 1100,
                },
                headers=headers,
            )
            assert r2.status_code == 201
            item = cast(dict[str, object], r2.json())
            item_id = cast(str, item["id"])
            assert item["list_id"] == list_id
            assert item["title"] == "喝水"
            assert item["tags"] == ["health"]
            assert item["tzid"] == "UTC"

            # Sync pull should include the created todo item.
            r_pull = await client.get(
                "/api/v2/sync/pull?cursor=0&limit=200",
                headers=headers,
            )
            assert r_pull.status_code == 200
            pull_body = cast(dict[str, object], r_pull.json())
            changes = cast(dict[str, object], pull_body.get("changes"))
            todo_items = cast(list[object], changes.get("todo_items"))
            assert any(cast(dict[str, object], x).get("id") == item_id for x in todo_items)

            # Patch item.
            r3 = await client.patch(
                f"/api/v2/todo/items/{item_id}",
                json={
                    "title": "喝水 2",
                    "tags": ["health", "daily"],
                    "tzid": "Asia/Tokyo",
                    "client_updated_at_ms": 1200,
                },
                headers=headers,
            )
            assert r3.status_code == 200
            patched = cast(dict[str, object], r3.json())
            assert patched["title"] == "喝水 2"
            assert patched["tags"] == ["health", "daily"]
            assert patched["tzid"] == "Asia/Tokyo"

            # Stale patch rejected with 409 conflict (server snapshot included).
            r_stale = await client.patch(
                f"/api/v2/todo/items/{item_id}",
                json={"title": "stale", "client_updated_at_ms": 10},
                headers=headers,
            )
            assert r_stale.status_code == 409
            err = cast(dict[str, object], r_stale.json())
            assert err.get("error") == "conflict"
            details = cast(dict[str, object], err.get("details"))
            snap = cast(dict[str, object], details.get("server_snapshot"))
            assert snap.get("id") == item_id

            # Delete.
            r_del = await client.delete(
                f"/api/v2/todo/items/{item_id}?client_updated_at_ms=1300",
                headers=headers,
            )
            assert r_del.status_code == 204

            # Deleted item hidden by default.
            r_list = await client.get(
                f"/api/v2/todo/items?list_id={list_id}&limit=200&offset=0",
                headers=headers,
            )
            assert r_list.status_code == 200
            body = cast(dict[str, object], r_list.json())
            ids = {cast(dict[str, object], x).get("id") for x in cast(list[object], body["items"])}
            assert item_id not in ids

            # include_deleted=true shows it.
            r_list2 = await client.get(
                f"/api/v2/todo/items?list_id={list_id}&include_deleted=true&limit=200&offset=0",
                headers=headers,
            )
            assert r_list2.status_code == 200
            body2 = cast(dict[str, object], r_list2.json())
            ids2 = {
                cast(dict[str, object], x).get("id") for x in cast(list[object], body2["items"])
            }
            assert item_id in ids2

            # Stale restore rejected.
            r_restore_stale = await client.post(
                f"/api/v2/todo/items/{item_id}/restore",
                json={"client_updated_at_ms": 100},
                headers=headers,
            )
            assert r_restore_stale.status_code == 409

            # Restore.
            r_restore = await client.post(
                f"/api/v2/todo/items/{item_id}/restore",
                json={"client_updated_at_ms": 1400},
                headers=headers,
            )
            assert r_restore.status_code == 200
            restored = cast(dict[str, object], r_restore.json())
            assert restored.get("deleted_at") is None
            assert restored.get("tzid") == "Asia/Tokyo"
    finally:
        settings.database_url = old_db
        settings.default_tzid = old_tzid
