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
async def test_notifications_mention_mark_read_and_unread_count(tmp_path: Path):
    old_db = settings.database_url
    old_secret = settings.share_token_secret
    old_public = settings.public_base_url
    try:
        settings.database_url = f"sqlite:///{tmp_path / 'test-notifications.db'}"
        settings.share_token_secret = "test-secret"
        settings.public_base_url = "http://test"
        reset_engine_cache()
        _alembic_upgrade_head()

        async with session_scope() as session:
            u1 = User(
                username="u1",
                password_hash="x",
                memos_id=None,
                memos_token="tok-u1",
                is_active=True,
            )
            u2 = User(
                username="u2",
                password_hash="x",
                memos_id=None,
                memos_token="tok-u2",
                is_active=True,
            )
            session.add(u1)
            session.add(u2)
            await session.commit()
            await session.refresh(u1)
            await session.refresh(u2)
            assert u1.id is not None
            assert u2.id is not None

            note = Note(
                id="note-1",
                user_id=int(u1.id),
                title="n1",
                body_md="hello",
                client_updated_at_ms=1,
                updated_at=utc_now(),
            )
            session.add(note)
            await session.commit()

        async with _make_async_client() as client:
            # Create a share as u1.
            r_share = await client.post(
                "/api/v1/notes/note-1/shares",
                headers={"Authorization": "Bearer tok-u1"},
                json={},
            )
            assert r_share.status_code == 201
            share_body = cast(dict[str, object], r_share.json())
            share_id = cast(str, share_body.get("share_id"))
            share_token = cast(str, share_body.get("share_token"))
            assert share_id
            assert share_token

            # Enable anonymous comments (no captcha to keep this test focused).
            r_cfg = await client.patch(
                f"/api/v1/shares/{share_id}/comment-config",
                headers={"Authorization": "Bearer tok-u1"},
                json={
                    "allow_anonymous_comments": True,
                    "anonymous_comments_require_captcha": False,
                },
            )
            assert r_cfg.status_code == 200

            # Create a public comment mentioning u2 twice (dedupe) and a non-existing u3.
            r_comment = await client.post(
                f"/api/v1/public/shares/{share_token}/comments",
                json={"body": "hi @u2 and again @u2 plus @u3"},
            )
            assert r_comment.status_code == 201
            comment_body = cast(dict[str, object], r_comment.json())
            comment_id = cast(str, comment_body.get("id"))
            assert comment_id

            # u2 gets 1 unread notification.
            r_unread = await client.get(
                "/api/v1/notifications/unread-count",
                headers={"Authorization": "Bearer tok-u2"},
            )
            assert r_unread.status_code == 200
            unread_body = cast(dict[str, object], r_unread.json())
            assert unread_body.get("unread_count") == 1

            r_list = await client.get(
                "/api/v1/notifications",
                headers={"Authorization": "Bearer tok-u2"},
                params={"unread_only": True},
            )
            assert r_list.status_code == 200
            list_body = cast(dict[str, object], r_list.json())
            notifs = cast(list[object], list_body.get("notifications"))
            assert len(notifs) == 1
            n0 = cast(dict[str, object], notifs[0])
            nid = cast(str, n0.get("id"))
            assert nid
            assert n0.get("kind") == "mention"
            payload = cast(dict[str, object], n0.get("payload"))
            assert payload.get("share_token") == share_token
            assert payload.get("note_id") == "note-1"
            assert payload.get("comment_id") == comment_id
            assert isinstance(payload.get("snippet"), str)

            # Mark read.
            r_read = await client.post(
                f"/api/v1/notifications/{nid}/read",
                headers={"Authorization": "Bearer tok-u2"},
            )
            assert r_read.status_code == 200
            read_body = cast(dict[str, object], r_read.json())
            assert read_body.get("read_at") is not None

            # Unread count updates.
            r_unread2 = await client.get(
                "/api/v1/notifications/unread-count",
                headers={"Authorization": "Bearer tok-u2"},
            )
            assert r_unread2.status_code == 200
            unread2_body = cast(dict[str, object], r_unread2.json())
            assert unread2_body.get("unread_count") == 0
    finally:
        settings.database_url = old_db
        settings.share_token_secret = old_secret
        settings.public_base_url = old_public
