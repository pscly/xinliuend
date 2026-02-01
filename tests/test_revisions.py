from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlmodel import select

from flow_backend.config import settings
from flow_backend.db import reset_engine_cache, session_scope
from flow_backend.main import app  # pyright: ignore[reportMissingTypeStubs]
from flow_backend.models import User, utc_now
from flow_backend.models_notes import Note, NoteRevision, NoteTag, Tag


def _make_async_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _alembic_upgrade_head() -> None:
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")


@pytest.mark.anyio
async def test_revision_restore_updates_note_and_creates_pre_restore_snapshot(tmp_path: Path):
    old_db = settings.database_url
    try:
        settings.database_url = f"sqlite:///{tmp_path / 'test-revisions.db'}"
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

            note = Note(
                id="note-1",
                user_id=user_id,
                title="current",
                body_md="current-body",
                client_updated_at_ms=1000,
                updated_at=utc_now(),
            )
            session.add(note)

            # Current tag on the note.
            tag = Tag(id="tag-1", user_id=user_id, name_original="Current", name_lower="current")
            nt = NoteTag(id="nt-1", user_id=user_id, note_id="note-1", tag_id="tag-1")
            session.add(tag)
            session.add(nt)

            # Seed a historical revision snapshot.
            rev_id = str(uuid.uuid4())
            session.add(
                NoteRevision(
                    id=rev_id,
                    user_id=user_id,
                    note_id="note-1",
                    kind="NORMAL",
                    reason=None,
                    snapshot_json={
                        "title": "old",
                        "body_md": "old-body",
                        "tags": ["t1"],
                        "client_updated_at_ms": 500,
                    },
                )
            )
            await session.commit()

        async with _make_async_client() as client:
            r = await client.post(
                f"/api/v2/notes/note-1/revisions/{rev_id}/restore",
                headers={"Authorization": "Bearer tok-u1"},
                json={"client_updated_at_ms": 2000},
            )
            assert r.status_code == 200
            body = cast(dict[str, object], r.json())
            assert body.get("id") == "note-1"
            assert body.get("title") == "old"
            assert body.get("body_md") == "old-body"
            assert body.get("client_updated_at_ms") == 2000
            tags = body.get("tags")
            assert isinstance(tags, list)
            assert "t1" in tags

        async with session_scope() as session:
            note_row = (
                await session.exec(
                    select(Note).where(Note.user_id == user_id).where(Note.id == "note-1")
                )
            ).first()
            assert note_row is not None
            assert note_row.title == "old"

            # A new revision should have been created with reason="restore".
            created = list(
                (
                    await session.exec(
                        select(NoteRevision)
                        .where(NoteRevision.user_id == user_id)
                        .where(NoteRevision.note_id == "note-1")
                        .where(NoteRevision.reason == "restore")
                    )
                ).all()
            )
            assert len(created) == 1
            snap = cast(dict[str, Any], created[0].snapshot_json)
            assert snap.get("title") == "current"

        # Stale restore should return 409.
        async with _make_async_client() as client:
            r2 = await client.post(
                f"/api/v2/notes/note-1/revisions/{rev_id}/restore",
                headers={"Authorization": "Bearer tok-u1"},
                json={"client_updated_at_ms": 10},
            )
            assert r2.status_code == 409
    finally:
        settings.database_url = old_db
