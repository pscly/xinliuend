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
async def test_v2_todo_items_tag_filter(tmp_path: Path):
    settings.database_url = f"sqlite:///{tmp_path / 'test-v2-todo-tag.db'}"
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
        list_id = r.json()["data"]["id"]

        r = await client.post(
            "/api/v1/todo/items",
            json={
                "list_id": list_id,
                "title": "喝水",
                "note": "",
                "status": "open",
                "priority": 1,
                "due_at_local": None,
                "completed_at_local": None,
                "sort_order": 1,
                "tags": ["health"],
                "is_recurring": False,
                "rrule": None,
                "dtstart_local": None,
                "tzid": "Asia/Shanghai",
                "reminders": [],
                "client_updated_at_ms": 1100,
            },
            headers=headers,
        )
        assert r.status_code == 200
        health_id = r.json()["data"]["id"]

        r = await client.post(
            "/api/v1/todo/items",
            json={
                "list_id": list_id,
                "title": "写周报",
                "note": "",
                "status": "open",
                "priority": 0,
                "due_at_local": None,
                "completed_at_local": None,
                "sort_order": 2,
                "tags": ["work"],
                "is_recurring": False,
                "rrule": None,
                "dtstart_local": None,
                "tzid": "Asia/Shanghai",
                "reminders": [],
                "client_updated_at_ms": 1200,
            },
            headers=headers,
        )
        assert r.status_code == 200
        work_id = r.json()["data"]["id"]

        r = await client.get(
            "/api/v2/todo/items?tag=health&limit=200&offset=0",
            headers=headers,
        )
        assert r.status_code == 200
        body = cast(dict[str, object], r.json())
        assert body.get("total") == 1
        items = cast(list[object], body.get("items"))
        assert len(items) == 1
        item0 = cast(dict[str, object], items[0])
        assert item0.get("id") == health_id
        assert item0.get("tags") == ["health"]

        r = await client.get(
            "/api/v2/todo/items?limit=1&offset=0",
            headers=headers,
        )
        assert r.status_code == 200
        body2 = cast(dict[str, object], r.json())
        assert body2.get("total") == 2
        assert body2.get("limit") == 1
        assert body2.get("offset") == 0

        # Sanity: ensure the other id exists in the unfiltered list.
        items2 = cast(list[object], body2.get("items"))
        got_ids = {cast(dict[str, object], x).get("id") for x in items2}
        assert health_id in got_ids or work_id in got_ids
