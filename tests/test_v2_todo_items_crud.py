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
            list_id = r.json()["id"]

            # Create item (tzid falls back to settings.default_tzid).
            r2 = await client.post(
                "/api/v1/todo/items",
                json={
                    "list_id": list_id,
                    "title": "喝水",
                    "tags": ["health"],
                    "client_updated_at_ms": 1100,
                },
                headers=headers,
            )
            assert r2.status_code == 200
            item_id = cast(str, r2.json()["id"])

            # Sync pull should include the created todo item.
            r_pull = await client.get(
                "/api/v1/sync/pull?cursor=0&limit=200",
                headers=headers,
            )
            assert r_pull.status_code == 200
            pull_body = cast(dict[str, object], r_pull.json())
            next_cursor = int(pull_body.get("next_cursor") or 0)
            changes = cast(dict[str, object], pull_body.get("changes"))
            todo_items = cast(list[object], changes.get("todo_items"))
            created = [
                cast(dict[str, object], x)
                for x in todo_items
                if cast(dict[str, object], x).get("id") == item_id
            ]
            assert created
            assert created[0].get("tzid") == "UTC"

            # Patch item.
            r3 = await client.patch(
                f"/api/v1/todo/items/{item_id}",
                json={
                    "title": "喝水 2",
                    "tags": ["health", "daily"],
                    "tzid": "Asia/Tokyo",
                    "client_updated_at_ms": 1200,
                },
                headers=headers,
            )
            assert r3.status_code == 200
            assert cast(dict[str, object], r3.json()).get("ok") is True

            r_pull2 = await client.get(
                f"/api/v1/sync/pull?cursor={next_cursor}&limit=200",
                headers=headers,
            )
            assert r_pull2.status_code == 200
            pull_body2 = cast(dict[str, object], r_pull2.json())
            changes2 = cast(dict[str, object], pull_body2.get("changes"))
            todo_items2 = cast(list[object], changes2.get("todo_items"))
            patched = [
                cast(dict[str, object], x)
                for x in todo_items2
                if cast(dict[str, object], x).get("id") == item_id
            ]
            assert patched
            assert patched[0].get("title") == "喝水 2"
            assert patched[0].get("tags") == ["health", "daily"]
            assert patched[0].get("tzid") == "Asia/Tokyo"

            # Stale patch rejected with 409 conflict.
            r_stale = await client.patch(
                f"/api/v1/todo/items/{item_id}",
                json={"title": "stale", "client_updated_at_ms": 10},
                headers=headers,
            )
            assert r_stale.status_code == 409
            err = cast(dict[str, object], r_stale.json())
            assert err.get("error") == "conflict"

            # Delete.
            r_del = await client.delete(
                f"/api/v1/todo/items/{item_id}?client_updated_at_ms=1300",
                headers=headers,
            )
            assert r_del.status_code == 200
            assert cast(dict[str, object], r_del.json()).get("ok") is True

            # Deleted item hidden by default.
            r_list = await client.get(
                f"/api/v1/todo/items?list_id={list_id}&limit=200&offset=0",
                headers=headers,
            )
            assert r_list.status_code == 200
            body = cast(dict[str, object], r_list.json())
            ids = {cast(dict[str, object], x).get("id") for x in cast(list[object], body["items"])}
            assert item_id not in ids

            # include_deleted=true shows it.
            r_list2 = await client.get(
                f"/api/v1/todo/items?list_id={list_id}&include_deleted=true&limit=200&offset=0",
                headers=headers,
            )
            assert r_list2.status_code == 200
            body2 = cast(dict[str, object], r_list2.json())
            ids2 = {
                cast(dict[str, object], x).get("id") for x in cast(list[object], body2["items"])
            }
            assert item_id in ids2

            # Stale restore rejected (v1 使用 upsert 实现“复活”语义)。
            r_restore_stale = await client.post(
                "/api/v1/todo/items",
                json={
                    "id": item_id,
                    "list_id": list_id,
                    "title": "喝水 2",
                    "tags": ["health", "daily"],
                    "tzid": "Asia/Tokyo",
                    "client_updated_at_ms": 100,
                },
                headers=headers,
            )
            assert r_restore_stale.status_code == 409

            # Restore (upsert).
            r_restore = await client.post(
                "/api/v1/todo/items",
                json={
                    "id": item_id,
                    "list_id": list_id,
                    "title": "喝水 2",
                    "tags": ["health", "daily"],
                    "tzid": "Asia/Tokyo",
                    "client_updated_at_ms": 1400,
                },
                headers=headers,
            )
            assert r_restore.status_code == 200
            assert cast(dict[str, object], r_restore.json()).get("id") == item_id

            r_list3 = await client.get(
                f"/api/v1/todo/items?list_id={list_id}&include_deleted=true&limit=200&offset=0",
                headers=headers,
            )
            assert r_list3.status_code == 200
            body3 = cast(dict[str, object], r_list3.json())
            items3 = cast(list[object], body3.get("items"))
            restored = [
                cast(dict[str, object], x)
                for x in items3
                if cast(dict[str, object], x).get("id") == item_id
            ]
            assert restored
            assert restored[0].get("deleted_at") is None
            assert restored[0].get("tzid") == "Asia/Tokyo"
    finally:
        settings.database_url = old_db
        settings.default_tzid = old_tzid
