from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from flow_backend.config import settings
from flow_backend.db import init_db, reset_engine_cache, session_scope
from flow_backend.main import app  # pyright: ignore[reportMissingTypeStubs]
from flow_backend.models import User
from flow_backend.security import hash_password


def _make_async_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.anyio
async def test_v1_todo_item_tzid_respects_payload_and_default(tmp_path: Path):
    old_db = settings.database_url
    old_tzid = settings.default_tzid
    try:
        settings.database_url = f"sqlite:///{tmp_path / 'test-v1-todo-tzid.db'}"
        settings.default_tzid = "UTC"
        reset_engine_cache()
        await init_db()

        async with session_scope() as session:
            session.add(
                User(
                    username="u1",
                    password_hash=hash_password("pass1234"),
                    memos_id=1,
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

            r = await client.post(
                "/api/v1/todo/items",
                json={
                    "list_id": list_id,
                    "title": "tzid custom",
                    "note": "",
                    "status": "open",
                    "priority": 0,
                    "due_at_local": None,
                    "completed_at_local": None,
                    "sort_order": 1,
                    "tags": [],
                    "is_recurring": False,
                    "rrule": None,
                    "dtstart_local": None,
                    "tzid": "Asia/Tokyo",
                    "reminders": [],
                    "client_updated_at_ms": 1100,
                },
                headers=headers,
            )
            assert r.status_code == 200

            r2 = await client.post(
                "/api/v1/todo/items",
                json={
                    "list_id": list_id,
                    "title": "tzid default",
                    "client_updated_at_ms": 1200,
                },
                headers=headers,
            )
            assert r2.status_code == 200

            r_list = await client.get(
                f"/api/v1/todo/items?list_id={list_id}",
                headers=headers,
            )
            assert r_list.status_code == 200
            items = r_list.json()["items"]
            assert any(
                it.get("title") == "tzid custom" and it.get("tzid") == "Asia/Tokyo" for it in items
            )
            assert any(
                it.get("title") == "tzid default" and it.get("tzid") == "UTC" for it in items
            )
    finally:
        settings.database_url = old_db
        settings.default_tzid = old_tzid
