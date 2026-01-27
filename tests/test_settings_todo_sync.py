from __future__ import annotations

from pathlib import Path

import pytest
import httpx

from flow_backend.config import settings
from flow_backend.db import init_db, reset_engine_cache, session_scope
from flow_backend.main import app
from flow_backend.models import User
from flow_backend.security import hash_password


def _make_async_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.anyio
async def test_settings_upsert_list_delete(tmp_path: Path):
    settings.database_url = f"sqlite:///{tmp_path / 'test.db'}"
    reset_engine_cache()
    await init_db()

    async with session_scope() as session:
        user = User(
            username="u1",
            password_hash=hash_password("pass1234"),
            memos_id=1,
            memos_token="tok-1",
            is_active=True,
        )
        session.add(user)
        await session.commit()

    headers = {"Authorization": "Bearer tok-1"}
    async with _make_async_client() as client:
        r = await client.put(
            "/api/v1/settings/theme",
            json={"value_json": {"dark": True}, "client_updated_at_ms": 1000},
            headers=headers,
        )
        assert r.status_code == 200

        r = await client.get("/api/v1/settings", headers=headers)
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert any(x["key"] == "theme" and x["value_json"]["dark"] is True for x in items)

        r = await client.request(
            "DELETE",
            "/api/v1/settings/theme",
            json={"client_updated_at_ms": 2000},
            headers=headers,
        )
        assert r.status_code == 200

        r = await client.get("/api/v1/settings", headers=headers)
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert all(x["key"] != "theme" for x in items)


@pytest.mark.anyio
async def test_todo_rrule_occurrence_and_sync_pull(tmp_path: Path):
    settings.database_url = f"sqlite:///{tmp_path / 'test2.db'}"
    reset_engine_cache()
    await init_db()

    async with session_scope() as session:
        user = User(
            username="u2",
            password_hash=hash_password("pass1234"),
            memos_id=2,
            memos_token="tok-2",
            is_active=True,
        )
        session.add(user)
        await session.commit()

    headers = {"Authorization": "Bearer tok-2"}
    async with _make_async_client() as client:
        # 创建 list
        r = await client.post(
            "/api/v1/todo/lists",
            json={
                "name": "inbox",
                "color": "blue",
                "sort_order": 1,
                "archived": False,
                "client_updated_at_ms": 1000,
            },
            headers=headers,
        )
        assert r.status_code == 200
        list_id = r.json()["data"]["id"]

        # 创建 recurring item
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
                "is_recurring": True,
                "rrule": "FREQ=DAILY;INTERVAL=1",
                "dtstart_local": "2026-01-24T09:00:00",
                "tzid": "Asia/Shanghai",
                "reminders": [],
                "client_updated_at_ms": 1100,
            },
            headers=headers,
        )
        assert r.status_code == 200
        item_id = r.json()["data"]["id"]

        # 单次完成（occurrence override）
        r = await client.post(
            "/api/v1/todo/occurrences",
            json={
                "item_id": item_id,
                "tzid": "Asia/Shanghai",
                "recurrence_id_local": "2026-01-24T09:00:00",
                "status_override": "done",
                "client_updated_at_ms": 1200,
            },
            headers=headers,
        )
        assert r.status_code == 200

        # sync pull 从 cursor=0 开始，应该能拿到变更
        r = await client.get("/api/v1/sync/pull?cursor=0&limit=50", headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["next_cursor"] >= 1
        changes = data["changes"]
        assert any(x["id"] == list_id for x in changes["todo_lists"])
        assert any(x["id"] == item_id for x in changes["todo_items"])
        assert any(
            x["item_id"] == item_id and x["recurrence_id_local"] == "2026-01-24T09:00:00"
            for x in changes["todo_occurrences"]
        )
