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
async def test_health_ok_has_request_id():
    async with _make_async_client() as client:
        r = await client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        assert r.headers.get("x-request-id")


@pytest.mark.anyio
async def test_openapi_includes_core_paths_and_x_request_id_header_param():
    async with _make_async_client() as client:
        r = await client.get("/openapi.json")
        assert r.status_code == 200
        data = cast(dict[str, object], r.json())
        paths_obj = data.get("paths", {})
        assert isinstance(paths_obj, dict)
        paths = cast(dict[str, object], paths_obj)
        assert "/health" in paths
        assert "/api/v1/notes" in paths

        # OpenAPI 应该文档化可选的入站 X-Request-Id header。
        notes_path_obj = paths.get("/api/v1/notes")
        assert isinstance(notes_path_obj, dict)
        notes_path = cast(dict[str, object], notes_path_obj)

        notes_get_obj = notes_path.get("get")
        assert isinstance(notes_get_obj, dict)
        notes_get = cast(dict[str, object], notes_get_obj)

        params_obj = notes_get.get("parameters", [])
        params = params_obj if isinstance(params_obj, list) else []
        assert any(
            isinstance(p, dict)
            and p.get("in") == "header"
            and isinstance(p.get("name"), str)
            and cast(str, p.get("name")).lower() == "x-request-id"
            for p in params
        )


@pytest.mark.anyio
async def test_v1_notes_list_pinned_shape(tmp_path: Path):
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
            "/api/v1/notes?limit=10&offset=5",
            headers={"Authorization": "Bearer tok-u1"},
        )
        assert r.status_code == 200
        body = cast(dict[str, object], r.json())
        assert body.get("items") == []
        assert body.get("total") == 0
        assert body.get("limit") == 10
        assert body.get("offset") == 5


@pytest.mark.anyio
async def test_v1_todo_items_list_shape(tmp_path: Path):
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
            "/api/v1/todo/items?limit=10&offset=5",
            headers={"Authorization": "Bearer tok-u1"},
        )
        assert r.status_code == 200
        body = cast(dict[str, object], r.json())
        assert body.get("items") == []


@pytest.mark.anyio
async def test_v1_sync_pull_pinned_shape():
    async with _make_async_client() as client:
        r = await client.get(
            "/api/v1/sync/pull?cursor=0&limit=200",
            headers={"Authorization": "Bearer tok-u1"},
        )
        # 需要鉴权；依赖测试顺序，token 在 DB 中可能存在也可能不存在。
        assert r.status_code in {200, 401}


@pytest.mark.anyio
async def test_v1_sync_pull_shape_with_auth(tmp_path: Path):
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
            "/api/v1/sync/pull?cursor=0&limit=200",
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
        # v1 sync 统一升级为 v2 风格，新增的资源也应存在（空列表即可）。
        assert changes.get("user_settings") == []
        assert changes.get("todo_lists") == []
        assert changes.get("todo_occurrences") == []
        assert changes.get("collection_items") == []


@pytest.mark.anyio
async def test_v1_sync_push_pinned_shape():
    async with _make_async_client() as client:
        r = await client.post(
            "/api/v1/sync/push",
            headers={"Authorization": "Bearer tok-u1"},
            json={"mutations": []},
        )
        assert r.status_code in {200, 401}


@pytest.mark.anyio
async def test_v1_sync_push_shape_with_auth(tmp_path: Path):
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
            "/api/v1/sync/push",
            headers={"Authorization": "Bearer tok-u1"},
            json={"mutations": []},
        )
        assert r.status_code == 200
        body = cast(dict[str, object], r.json())
        assert isinstance(body.get("cursor"), int)
        assert body.get("applied") == []
        assert body.get("rejected") == []


@pytest.mark.anyio
async def test_v1_errors_use_error_response_shape_and_have_request_id_header():
    async with _make_async_client() as client:
        r = await client.get("/api/v1/this-route-does-not-exist")
        assert r.status_code == 404
        body = cast(dict[str, object], r.json())

        assert "detail" not in body
        assert isinstance(body.get("error"), str)
        assert isinstance(body.get("message"), str)
        assert isinstance(body.get("request_id"), str)

        # Request id header should be injected.
        assert r.headers.get("x-request-id")


@pytest.mark.anyio
async def test_v2_removed_returns_404_and_error_response_shape():
    async with _make_async_client() as client:
        r = await client.get("/api/v2/notes")
        assert r.status_code == 404

        body = cast(dict[str, object], r.json())
        assert "detail" not in body
        assert isinstance(body.get("error"), str)
        assert isinstance(body.get("message"), str)
        assert isinstance(body.get("request_id"), str)

        assert r.headers.get("x-request-id")
