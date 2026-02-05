from __future__ import annotations

from pathlib import Path
from typing import cast

import httpx
import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from flow_backend.config import settings
from flow_backend.db import reset_engine_cache, session_scope
from flow_backend.main import app  # pyright: ignore[reportMissingTypeStubs]
from flow_backend.models import User, utc_now
from flow_backend.models_notes import Note, NoteTag, Tag


def _make_async_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _alembic_upgrade_head() -> None:
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")


@pytest.mark.anyio
async def test_notes_search_sqlite_fts5_end_to_end(tmp_path: Path):
    settings.database_url = f"sqlite:///{tmp_path / 'test-notes-search.db'}"
    reset_engine_cache()
    _alembic_upgrade_head()

    async with session_scope() as session:
        user = User(
            username="u1",
            password_hash="x",
            memos_id=None,
            memos_token="tok-u1",
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        assert user.id is not None
        user_id = int(user.id)

        # Ensure FTS table exists (migration created it).
        await session.execute(sa.text("SELECT 1 FROM notes_fts LIMIT 1"))

        # Seed notes.
        n1 = Note(
            id="note-1",
            user_id=user_id,
            title="Hello world",
            body_md="some body",
            client_updated_at_ms=1,
            updated_at=utc_now(),
        )
        n2 = Note(
            id="note-2",
            user_id=user_id,
            title="Other",
            body_md="hello from body",
            client_updated_at_ms=2,
            updated_at=utc_now(),
        )

        # A deleted note should not be indexed by FTS triggers.
        n3 = Note(
            id="note-3",
            user_id=user_id,
            title="hello deleted",
            body_md="should not show up",
            deleted_at=utc_now(),
            client_updated_at_ms=3,
            updated_at=utc_now(),
        )

        session.add(n1)
        session.add(n2)
        session.add(n3)

        # Add a tag to note-1 to verify tag intersection with FTS.
        t1 = Tag(id="tag-1", user_id=user_id, name_original="Work", name_lower="work")
        nt1 = NoteTag(id="nt-1", user_id=user_id, note_id="note-1", tag_id="tag-1")
        session.add(t1)
        session.add(nt1)

        await session.commit()

        # Trigger should have indexed note-1 and note-2 only.
        count = (await session.execute(sa.text("SELECT COUNT(*) FROM notes_fts"))).scalar_one()
        assert int(count or 0) == 2

    async with _make_async_client() as client:
        r = await client.get(
            "/api/v1/notes?q=hello",
            headers={"Authorization": "Bearer tok-u1"},
        )
        assert r.status_code == 200
        body = cast(dict[str, object], r.json())
        assert body.get("total") == 2
        items_obj = body.get("items")
        assert isinstance(items_obj, list)
        ids = {cast(dict[str, object], it).get("id") for it in items_obj}
        assert ids == {"note-1", "note-2"}

        r2 = await client.get(
            "/api/v1/notes?q=hello&tag=work",
            headers={"Authorization": "Bearer tok-u1"},
        )
        assert r2.status_code == 200
        body2 = cast(dict[str, object], r2.json())
        assert body2.get("total") == 1
        items_obj2 = body2.get("items")
        assert isinstance(items_obj2, list)
        assert {cast(dict[str, object], it).get("id") for it in items_obj2} == {"note-1"}
