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


@pytest.mark.anyio
async def test_v2_notes_crud_and_conflict(tmp_path: Path):
    old_db = settings.database_url
    try:
        settings.database_url = f"sqlite:///{tmp_path / 'test-v2-notes.db'}"
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

        async with _make_async_client() as client:
            # Create
            r = await client.post(
                "/api/v2/notes",
                headers={"Authorization": "Bearer tok-u1"},
                json={
                    "body_md": "Hello\nworld",
                    "tags": ["Work"],
                    "client_updated_at_ms": 1000,
                },
            )
            assert r.status_code == 201
            body = cast(dict[str, object], r.json())
            note_id = cast(str, body.get("id"))
            assert note_id
            assert body.get("title") == "Hello"
            assert body.get("tags") == ["Work"]

            # List by tag (case-insensitive exact match).
            r_list = await client.get(
                "/api/v2/notes?tag=work&limit=10&offset=0",
                headers={"Authorization": "Bearer tok-u1"},
            )
            assert r_list.status_code == 200
            items = cast(dict[str, object], r_list.json()).get("items")
            assert isinstance(items, list)
            assert any(cast(dict[str, object], it).get("id") == note_id for it in items)

            # Patch
            r_patch = await client.patch(
                f"/api/v2/notes/{note_id}",
                headers={"Authorization": "Bearer tok-u1"},
                json={
                    "body_md": "New body",
                    "client_updated_at_ms": 2000,
                },
            )
            assert r_patch.status_code == 200
            patched = cast(dict[str, object], r_patch.json())
            assert patched.get("body_md") == "New body"
            assert patched.get("client_updated_at_ms") == 2000

            # Conflict on stale update.
            r_conf = await client.patch(
                f"/api/v2/notes/{note_id}",
                headers={"Authorization": "Bearer tok-u1"},
                json={
                    "title": "stale",
                    "client_updated_at_ms": 10,
                },
            )
            assert r_conf.status_code == 409
            conf_body = cast(dict[str, object], r_conf.json())
            assert conf_body.get("error") == "conflict"
            details = conf_body.get("details")
            assert isinstance(details, dict)
            assert "server_snapshot" in details

            # Revisions should include an update snapshot.
            r_revs = await client.get(
                f"/api/v2/notes/{note_id}/revisions",
                headers={"Authorization": "Bearer tok-u1"},
            )
            assert r_revs.status_code == 200
            rev_items = cast(dict[str, object], r_revs.json()).get("items")
            assert isinstance(rev_items, list)
            assert any(cast(dict[str, Any], it).get("reason") == "update" for it in rev_items)

            # Delete
            r_del = await client.delete(
                f"/api/v2/notes/{note_id}?client_updated_at_ms=3000",
                headers={"Authorization": "Bearer tok-u1"},
            )
            assert r_del.status_code == 204

            # Get without include_deleted should 404.
            r_get = await client.get(
                f"/api/v2/notes/{note_id}",
                headers={"Authorization": "Bearer tok-u1"},
            )
            assert r_get.status_code == 404

            # Restore
            r_restore = await client.post(
                f"/api/v2/notes/{note_id}/restore",
                headers={"Authorization": "Bearer tok-u1"},
                json={"client_updated_at_ms": 4000},
            )
            assert r_restore.status_code == 200
            restored = cast(dict[str, object], r_restore.json())
            assert restored.get("deleted_at") is None
            assert restored.get("client_updated_at_ms") == 4000
    finally:
        settings.database_url = old_db
