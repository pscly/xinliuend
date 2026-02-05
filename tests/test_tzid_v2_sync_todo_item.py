from __future__ import annotations

from pathlib import Path
from typing import cast
from uuid import uuid4

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
async def test_v2_sync_todo_item_tzid_preserved_and_default(tmp_path: Path):
    old_db = settings.database_url
    old_tzid = settings.default_tzid
    try:
        settings.database_url = f"sqlite:///{tmp_path / 'test-v2-todo-tzid.db'}"
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

            id_default = str(uuid4())
            id_custom = str(uuid4())

            r_push = await client.post(
                "/api/v1/sync/push",
                headers=headers,
                json={
                    "mutations": [
                        {
                            "resource": "todo_item",
                            "entity_id": id_default,
                            "op": "upsert",
                            "client_updated_at_ms": 1100,
                            "data": {
                                "list_id": list_id,
                                "title": "default tzid",
                                "tags": [],
                            },
                        },
                        {
                            "resource": "todo_item",
                            "entity_id": id_custom,
                            "op": "upsert",
                            "client_updated_at_ms": 1200,
                            "data": {
                                "list_id": list_id,
                                "title": "custom tzid",
                                "tags": [],
                                "tzid": "Asia/Tokyo",
                            },
                        },
                    ]
                },
            )
            assert r_push.status_code == 200

            r_list = await client.get(
                "/api/v1/todo/items?limit=200&offset=0",
                headers=headers,
            )
            assert r_list.status_code == 200
            body = cast(dict[str, object], r_list.json())
            items = cast(list[object], body.get("items"))
            tz_by_id = {
                cast(dict[str, object], it)["id"]: cast(dict[str, object], it)["tzid"]
                for it in items
            }
            assert tz_by_id.get(id_default) == "UTC"
            assert tz_by_id.get(id_custom) == "Asia/Tokyo"
    finally:
        settings.database_url = old_db
        settings.default_tzid = old_tzid
