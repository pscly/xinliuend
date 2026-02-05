from __future__ import annotations

from pathlib import Path
from typing import cast

import httpx
import pytest
from alembic import command
from alembic.config import Config

from flow_backend.config import settings
from flow_backend.db import reset_engine_cache, session_scope
from flow_backend.main import app  # pyright: ignore[reportMissingTypeStubs]
from flow_backend.models import User, utc_now
from flow_backend.models_notes import Note


def _make_async_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _alembic_upgrade_head() -> None:
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")


@pytest.mark.anyio
async def test_attachments_upload_and_download_local_storage(tmp_path: Path):
    old_db = settings.database_url
    old_dir = settings.attachments_local_dir
    old_max = settings.attachments_max_size_bytes
    try:
        settings.database_url = f"sqlite:///{tmp_path / 'test-attachments.db'}"
        settings.attachments_local_dir = str(tmp_path / "attachments")
        settings.attachments_max_size_bytes = 25 * 1024 * 1024
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
                title="n1",
                body_md="hello",
                client_updated_at_ms=1,
                updated_at=utc_now(),
            )
            session.add(note)
            await session.commit()

        async with _make_async_client() as client:
            r = await client.post(
                "/api/v1/notes/note-1/attachments",
                headers={"Authorization": "Bearer tok-u1"},
                files={"file": ("hello.txt", b"hello", "text/plain")},
            )
            assert r.status_code == 201
            body = cast(dict[str, object], r.json())
            assert body.get("note_id") == "note-1"
            attachment_id = cast(str, body.get("id"))
            assert attachment_id

            # Local storage layout is pinned: {root}/{user_id}/{attachment_id}
            expected_path = Path(settings.attachments_local_dir) / str(user_id) / attachment_id
            assert expected_path.exists()

            r2 = await client.get(
                f"/api/v1/attachments/{attachment_id}",
                headers={"Authorization": "Bearer tok-u1"},
            )
            assert r2.status_code == 200
            assert r2.content == b"hello"

            # Another user cannot access this attachment.
            async with session_scope() as session:
                session.add(
                    User(
                        username="u2",
                        password_hash="x",
                        memos_id=None,
                        memos_token="tok-u2",
                        is_active=True,
                    )
                )
                await session.commit()

            r3 = await client.get(
                f"/api/v1/attachments/{attachment_id}",
                headers={"Authorization": "Bearer tok-u2"},
            )
            assert r3.status_code == 404
    finally:
        settings.database_url = old_db
        settings.attachments_local_dir = old_dir
        settings.attachments_max_size_bytes = old_max


@pytest.mark.anyio
async def test_attachments_upload_rejects_too_large(tmp_path: Path):
    old_db = settings.database_url
    old_dir = settings.attachments_local_dir
    old_max = settings.attachments_max_size_bytes
    try:
        settings.database_url = f"sqlite:///{tmp_path / 'test-attachments-too-large.db'}"
        settings.attachments_local_dir = str(tmp_path / "attachments")
        settings.attachments_max_size_bytes = 4
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

            note = Note(
                id="note-1",
                user_id=int(user.id),
                title="n1",
                body_md="hello",
                client_updated_at_ms=1,
                updated_at=utc_now(),
            )
            session.add(note)
            await session.commit()

        async with _make_async_client() as client:
            r = await client.post(
                "/api/v1/notes/note-1/attachments",
                headers={"Authorization": "Bearer tok-u1"},
                files={"file": ("big.txt", b"hello", "text/plain")},
            )
            assert r.status_code == 413
    finally:
        settings.database_url = old_db
        settings.attachments_local_dir = old_dir
        settings.attachments_max_size_bytes = old_max
