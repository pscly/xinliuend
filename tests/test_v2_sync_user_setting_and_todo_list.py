from __future__ import annotations

from pathlib import Path
from typing import Any, cast

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


def _find_by_key(items: list[object], key: str) -> dict[str, Any] | None:
    for it in items:
        d = cast(dict[str, Any], it)
        if d.get("key") == key:
            return d
    return None


def _find_by_id(items: list[object], entity_id: str) -> dict[str, Any] | None:
    for it in items:
        d = cast(dict[str, Any], it)
        if d.get("id") == entity_id:
            return d
    return None


def _find_rejected(rejected: list[object], entity_id: str) -> dict[str, Any] | None:
    for it in rejected:
        d = cast(dict[str, Any], it)
        if d.get("entity_id") == entity_id:
            return d
    return None


@pytest.mark.anyio
async def test_v2_sync_user_setting_and_todo_list_pull_conflict_and_tombstone(
    tmp_path: Path,
) -> None:
    old_db = settings.database_url
    try:
        settings.database_url = f"sqlite:///{tmp_path / 'test-v2-sync-setting-list.db'}"
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

        headers = {"Authorization": "Bearer tok-u1"}
        setting_key = "theme"
        list_id = "todo-list-1"

        async with _make_async_client() as client:
            r = await client.post(
                "/api/v1/sync/push",
                headers=headers,
                json={
                    "mutations": [
                        {
                            "resource": "user_setting",
                            "entity_id": setting_key,
                            "op": "upsert",
                            "client_updated_at_ms": 1000,
                            "data": {"value_json": {"dark": True}},
                        },
                        {
                            "resource": "todo_list",
                            "entity_id": list_id,
                            "op": "upsert",
                            "client_updated_at_ms": 1100,
                            "data": {
                                "name": "Inbox",
                                "color": None,
                                "sort_order": 1,
                                "archived": False,
                            },
                        },
                    ]
                },
            )
            assert r.status_code == 200
            push_body = cast(dict[str, Any], r.json())
            applied = cast(list[object], push_body.get("applied"))
            assert any(cast(dict[str, Any], a).get("entity_id") == setting_key for a in applied)
            assert any(cast(dict[str, Any], a).get("entity_id") == list_id for a in applied)

            r2 = await client.get(
                "/api/v1/sync/pull?cursor=0&limit=200",
                headers=headers,
            )
            assert r2.status_code == 200
            pull_body = cast(dict[str, Any], r2.json())
            changes = cast(dict[str, Any], pull_body.get("changes"))

            got_setting = _find_by_key(
                cast(list[object], changes.get("user_settings")), setting_key
            )
            assert got_setting is not None
            assert got_setting.get("deleted_at") is None
            value_json = cast(dict[str, Any], got_setting.get("value_json"))
            assert value_json.get("dark") is True

            got_list = _find_by_id(cast(list[object], changes.get("todo_lists")), list_id)
            assert got_list is not None
            assert got_list.get("name") == "Inbox"
            assert got_list.get("deleted_at") is None

            r3 = await client.post(
                "/api/v1/sync/push",
                headers=headers,
                json={
                    "mutations": [
                        {
                            "resource": "user_setting",
                            "entity_id": setting_key,
                            "op": "upsert",
                            "client_updated_at_ms": 10,
                            "data": {"value_json": {"dark": False}},
                        },
                        {
                            "resource": "todo_list",
                            "entity_id": list_id,
                            "op": "upsert",
                            "client_updated_at_ms": 10,
                            "data": {"name": "STALE"},
                        },
                    ]
                },
            )
            assert r3.status_code == 200
            push2 = cast(dict[str, Any], r3.json())
            rejected = cast(list[object], push2.get("rejected"))

            rej_setting = _find_rejected(rejected, setting_key)
            assert rej_setting is not None
            assert rej_setting.get("reason") == "conflict"
            server_setting = cast(dict[str, Any], rej_setting.get("server"))
            assert int(cast(int, server_setting.get("client_updated_at_ms"))) == 1000

            rej_list = _find_rejected(rejected, list_id)
            assert rej_list is not None
            assert rej_list.get("reason") == "conflict"
            server_list = cast(dict[str, Any], rej_list.get("server"))
            assert int(cast(int, server_list.get("client_updated_at_ms"))) == 1100

            r4 = await client.post(
                "/api/v1/sync/push",
                headers=headers,
                json={
                    "mutations": [
                        {
                            "resource": "user_setting",
                            "entity_id": setting_key,
                            "op": "delete",
                            "client_updated_at_ms": 2000,
                        },
                        {
                            "resource": "todo_list",
                            "entity_id": list_id,
                            "op": "delete",
                            "client_updated_at_ms": 2100,
                        },
                    ]
                },
            )
            assert r4.status_code == 200

            r5 = await client.get(
                "/api/v1/sync/pull?cursor=0&limit=500",
                headers=headers,
            )
            assert r5.status_code == 200
            pull2 = cast(dict[str, Any], r5.json())
            changes2 = cast(dict[str, Any], pull2.get("changes"))

            got_setting2 = _find_by_key(
                cast(list[object], changes2.get("user_settings")), setting_key
            )
            assert got_setting2 is not None
            assert got_setting2.get("deleted_at") is not None

            got_list2 = _find_by_id(cast(list[object], changes2.get("todo_lists")), list_id)
            assert got_list2 is not None
            assert got_list2.get("deleted_at") is not None
    finally:
        settings.database_url = old_db
