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
from flow_backend.user_session import make_user_session
from flow_backend.v2.schemas.errors import ErrorResponse


def _make_async_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _alembic_upgrade_head() -> None:
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_user(*, username: str, token: str) -> int:
    async with session_scope() as session:
        user = User(username=username, password_hash="x", memos_token=token, is_active=True)
        session.add(user)
        await session.commit()
        await session.refresh(user)

        user_id = user.id
        assert user_id is not None
        return int(user_id)


@pytest.mark.anyio
async def test_collections_requires_auth_and_bearer_isolation_recursive_delete_and_move_cycle(
    tmp_path: Path,
) -> None:
    old_db = settings.database_url
    try:
        settings.database_url = f"sqlite:///{tmp_path / 'test-collections-api.db'}"
        reset_engine_cache()
        _alembic_upgrade_head()

        user_a_id = await _create_user(username="u_col_a", token="tok-u_col_a")
        _ = user_a_id
        user_b_id = await _create_user(username="u_col_b", token="tok-u_col_b")
        _ = user_b_id

        async with _make_async_client() as client:
            r401 = await client.get("/api/v1/collections/items")
            assert r401.status_code == 401
            err401 = ErrorResponse.model_validate(r401.json())
            assert err401.error == "unauthorized"

            parent_id = "00000000-0000-0000-0000-000000000001"
            child_folder_id = "00000000-0000-0000-0000-000000000002"
            child_ref_id = "00000000-0000-0000-0000-000000000003"

            r_parent = await client.post(
                "/api/v1/collections/items",
                headers=_bearer("tok-u_col_a"),
                json={
                    "id": parent_id,
                    "item_type": "folder",
                    "parent_id": None,
                    "name": "parent",
                    "sort_order": 1,
                    "client_updated_at_ms": 1000,
                },
            )
            assert r_parent.status_code == 201

            r_child_folder = await client.post(
                "/api/v1/collections/items",
                headers=_bearer("tok-u_col_a"),
                json={
                    "id": child_folder_id,
                    "item_type": "folder",
                    "parent_id": parent_id,
                    "name": "child",
                    "sort_order": 1,
                    "client_updated_at_ms": 1100,
                },
            )
            assert r_child_folder.status_code == 201

            r_child_ref = await client.post(
                "/api/v1/collections/items",
                headers=_bearer("tok-u_col_a"),
                json={
                    "id": child_ref_id,
                    "item_type": "note_ref",
                    "parent_id": child_folder_id,
                    "ref_type": "flow_note",
                    "ref_id": "note-1",
                    "sort_order": 1,
                    "client_updated_at_ms": 1200,
                },
            )
            assert r_child_ref.status_code == 201

            r_list_b = await client.get(
                f"/api/v1/collections/items?parent_id={parent_id}",
                headers=_bearer("tok-u_col_b"),
            )
            assert r_list_b.status_code == 200
            body_list_b = cast(dict[str, Any], r_list_b.json())
            assert cast(int, body_list_b.get("total")) == 0
            assert cast(list[object], body_list_b.get("items")) == []

            r_patch_b = await client.patch(
                f"/api/v1/collections/items/{child_folder_id}",
                headers=_bearer("tok-u_col_b"),
                json={"name": "hacked", "client_updated_at_ms": 2000},
            )
            assert r_patch_b.status_code == 404
            err_patch_b = ErrorResponse.model_validate(r_patch_b.json())
            assert err_patch_b.error == "not_found"
            assert err_patch_b.message == "item not found"

            r_del_b = await client.delete(
                f"/api/v1/collections/items/{child_folder_id}?client_updated_at_ms=2000",
                headers=_bearer("tok-u_col_b"),
            )
            assert r_del_b.status_code == 404
            err_del_b = ErrorResponse.model_validate(r_del_b.json())
            assert err_del_b.error == "not_found"
            assert err_del_b.message == "item not found"

            a_id = "00000000-0000-0000-0000-000000000010"
            b_id = "00000000-0000-0000-0000-000000000011"
            r_a = await client.post(
                "/api/v1/collections/items",
                headers=_bearer("tok-u_col_a"),
                json={
                    "id": a_id,
                    "item_type": "folder",
                    "parent_id": None,
                    "name": "A",
                    "sort_order": 1,
                    "client_updated_at_ms": 1300,
                },
            )
            assert r_a.status_code == 201
            r_b = await client.post(
                "/api/v1/collections/items",
                headers=_bearer("tok-u_col_a"),
                json={
                    "id": b_id,
                    "item_type": "folder",
                    "parent_id": a_id,
                    "name": "B",
                    "sort_order": 1,
                    "client_updated_at_ms": 1400,
                },
            )
            assert r_b.status_code == 201

            r_cycle = await client.patch(
                "/api/v1/collections/items/move",
                headers=_bearer("tok-u_col_a"),
                json={
                    "items": [
                        {
                            "id": a_id,
                            "parent_id": b_id,
                            "sort_order": 1,
                            "client_updated_at_ms": 3000,
                        }
                    ]
                },
            )
            assert r_cycle.status_code == 400, r_cycle.json()
            err_cycle = ErrorResponse.model_validate(r_cycle.json())
            assert err_cycle.error == "bad_request"

            r_del_parent = await client.delete(
                f"/api/v1/collections/items/{parent_id}?client_updated_at_ms=5000",
                headers=_bearer("tok-u_col_a"),
            )
            assert r_del_parent.status_code == 204

            r_children_default = await client.get(
                f"/api/v1/collections/items?parent_id={parent_id}",
                headers=_bearer("tok-u_col_a"),
            )
            assert r_children_default.status_code == 200
            body_default = cast(dict[str, Any], r_children_default.json())
            assert cast(list[object], body_default.get("items")) == []

            r_children_deleted = await client.get(
                f"/api/v1/collections/items?parent_id={parent_id}&include_deleted=true",
                headers=_bearer("tok-u_col_a"),
            )
            assert r_children_deleted.status_code == 200
            body_deleted = cast(dict[str, Any], r_children_deleted.json())
            items_deleted = cast(list[object], body_deleted.get("items"))
            assert any(
                cast(dict[str, Any], it).get("id") == child_folder_id
                and cast(dict[str, Any], it).get("deleted_at") is not None
                for it in items_deleted
            )

            r_grandchildren_deleted = await client.get(
                f"/api/v1/collections/items?parent_id={child_folder_id}&include_deleted=true",
                headers=_bearer("tok-u_col_a"),
            )
            assert r_grandchildren_deleted.status_code == 200
            body_grand = cast(dict[str, Any], r_grandchildren_deleted.json())
            items_grand = cast(list[object], body_grand.get("items"))
            assert any(
                cast(dict[str, Any], it).get("id") == child_ref_id
                and cast(dict[str, Any], it).get("deleted_at") is not None
                for it in items_grand
            )

            r_pull = await client.get(
                "/api/v1/sync/pull?cursor=0&limit=500",
                headers=_bearer("tok-u_col_a"),
            )
            assert r_pull.status_code == 200
            pull_body = cast(dict[str, Any], r_pull.json())
            changes = cast(dict[str, Any], pull_body.get("changes"))
            collection_items = cast(list[object], changes.get("collection_items"))
            ids = {cast(str, cast(dict[str, Any], it).get("id")) for it in collection_items}
            assert parent_id in ids
            assert child_folder_id in ids
            assert child_ref_id in ids

            leaf = next(
                cast(dict[str, Any], it)
                for it in collection_items
                if cast(dict[str, Any], it).get("id") == child_ref_id
            )
            assert leaf.get("deleted_at") is not None
    finally:
        settings.database_url = old_db


@pytest.mark.anyio
async def test_collections_cookie_session_csrf_enforced_on_create(tmp_path: Path) -> None:
    old_db = settings.database_url
    old_secret = settings.user_session_secret
    try:
        settings.database_url = f"sqlite:///{tmp_path / 'test-collections-cookie-csrf.db'}"
        settings.user_session_secret = "test-secret"
        reset_engine_cache()
        _alembic_upgrade_head()

        user_id = await _create_user(username="u_col_cookie", token="tok-u_col_cookie")
        csrf_token = "csrf-token-collections"
        cookie_value = make_user_session(csrf_token=csrf_token, user_id=user_id)

        async with _make_async_client() as client:
            client.cookies.set(settings.user_session_cookie_name, cookie_value)

            r = await client.post(
                "/api/v1/collections/items",
                json={
                    "item_type": "folder",
                    "parent_id": None,
                    "name": "cookie-folder",
                    "sort_order": 1,
                    "client_updated_at_ms": 1000,
                },
            )
            assert r.status_code == 403
            err = ErrorResponse.model_validate(r.json())
            assert err.error == "forbidden"
            assert err.message == "csrf failed"

            r2 = await client.post(
                "/api/v1/collections/items",
                json={
                    "item_type": "folder",
                    "parent_id": None,
                    "name": "cookie-folder",
                    "sort_order": 1,
                    "client_updated_at_ms": 1100,
                },
                headers={settings.user_csrf_header_name: csrf_token},
            )
            assert r2.status_code == 201
            payload = cast(dict[str, Any], r2.json())
            assert payload.get("item_type") == "folder"
            assert payload.get("name") == "cookie-folder"
    finally:
        settings.database_url = old_db
        settings.user_session_secret = old_secret
