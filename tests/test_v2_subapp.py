from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from typing import cast

from flow_backend.config import settings
from flow_backend.db import init_db, reset_engine_cache, session_scope
from flow_backend.main import app  # pyright: ignore[reportMissingTypeStubs]
from flow_backend.models import User


def _make_async_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.anyio
async def test_v2_health_ok():
    async with _make_async_client() as client:
        r = await client.get("/api/v2/health")
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        assert r.headers.get("x-request-id")


@pytest.mark.anyio
async def test_v2_openapi_includes_core_paths():
    async with _make_async_client() as client:
        r = await client.get("/api/v2/openapi.json")
        assert r.status_code == 200
        data = cast(dict[str, object], r.json())
        paths_obj = data.get("paths", {})
        assert isinstance(paths_obj, dict)
        paths = cast(dict[str, object], paths_obj)
        assert "/health" in paths
        assert "/notes" in paths


@pytest.mark.anyio
async def test_v2_notes_list_pinned_shape(tmp_path: Path):
    settings.database_url = f"sqlite:///{tmp_path / 'test-v2-notes.db'}"
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

    async with _make_async_client() as client:
        r = await client.get(
            "/api/v2/notes?limit=10&offset=5",
            headers={"Authorization": "Bearer tok-u1"},
        )
        assert r.status_code == 200
        body = cast(dict[str, object], r.json())
        assert body.get("items") == []
        assert body.get("total") == 0
        assert body.get("limit") == 10
        assert body.get("offset") == 5


@pytest.mark.anyio
async def test_v2_todo_items_list_pinned_shape(tmp_path: Path):
    settings.database_url = f"sqlite:///{tmp_path / 'test-v2-todo-items.db'}"
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

    async with _make_async_client() as client:
        r = await client.get(
            "/api/v2/todo/items?limit=10&offset=5",
            headers={"Authorization": "Bearer tok-u1"},
        )
        assert r.status_code == 200
        body = cast(dict[str, object], r.json())
        assert body.get("items") == []
        assert body.get("total") == 0
        assert body.get("limit") == 10
        assert body.get("offset") == 5


@pytest.mark.anyio
async def test_v2_sync_pull_pinned_shape():
    async with _make_async_client() as client:
        r = await client.get(
            "/api/v2/sync/pull?cursor=0&limit=200",
            headers={"Authorization": "Bearer tok-u1"},
        )
        # Require auth; depending on test order the token may or may not exist in DB.
        assert r.status_code in {200, 401}


@pytest.mark.anyio
async def test_v2_sync_pull_shape_with_auth(tmp_path: Path):
    settings.database_url = f"sqlite:///{tmp_path / 'test-v2-sync-pull.db'}"
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

    async with _make_async_client() as client:
        r = await client.get(
            "/api/v2/sync/pull?cursor=0&limit=200",
            headers={"Authorization": "Bearer tok-u1"},
        )
        assert r.status_code == 200
        body = cast(dict[str, object], r.json())
        assert body.get("cursor") == 0
        assert body.get("next_cursor") == 0
        assert body.get("has_more") is False

        changes_obj = body.get("changes")
        assert isinstance(changes_obj, dict)
        changes = cast(dict[str, object], changes_obj)
        assert changes.get("notes") == []
        assert changes.get("todo_items") == []


@pytest.mark.anyio
async def test_v2_sync_push_pinned_shape():
    async with _make_async_client() as client:
        r = await client.post(
            "/api/v2/sync/push",
            headers={"Authorization": "Bearer tok-u1"},
            json={"mutations": []},
        )
        assert r.status_code in {200, 401}


@pytest.mark.anyio
async def test_v2_sync_push_shape_with_auth(tmp_path: Path):
    settings.database_url = f"sqlite:///{tmp_path / 'test-v2-sync-push.db'}"
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

    async with _make_async_client() as client:
        r = await client.post(
            "/api/v2/sync/push",
            headers={"Authorization": "Bearer tok-u1"},
            json={"mutations": []},
        )
        assert r.status_code == 200
        body = cast(dict[str, object], r.json())
        assert isinstance(body.get("cursor"), int)
        assert body.get("applied") == []
        assert body.get("rejected") == []


@pytest.mark.anyio
async def test_v1_error_shape_unchanged_and_has_request_id_header():
    async with _make_async_client() as client:
        r = await client.get("/api/v1/this-route-does-not-exist")
        assert r.status_code == 404
        body = cast(dict[str, object], r.json())

        # v1 should keep FastAPI default error shape.
        assert "detail" in body
        assert "error" not in body

        # Request id header should be injected for v1 too.
        assert r.headers.get("x-request-id")


@pytest.mark.anyio
async def test_v2_errors_use_error_response_shape_and_have_request_id_header():
    async with _make_async_client() as client:
        # Trigger an HTTPException inside v2 without adding extra routes.
        r = await client.get("/api/v2/notes")
        assert r.status_code == 401

        body = cast(dict[str, object], r.json())
        assert "detail" not in body
        assert isinstance(body.get("error"), str)
        assert isinstance(body.get("message"), str)
        assert isinstance(body.get("request_id"), str)

        assert r.headers.get("x-request-id")
