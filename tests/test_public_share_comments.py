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
async def test_public_share_comments_captcha_report_and_attachment_upload(tmp_path: Path):
    old_db = settings.database_url
    old_dir = settings.attachments_local_dir
    old_secret = settings.share_token_secret
    old_public = settings.public_base_url
    try:
        settings.database_url = f"sqlite:///{tmp_path / 'test-public-comments.db'}"
        settings.attachments_local_dir = str(tmp_path / "attachments")
        settings.share_token_secret = "test-secret"
        settings.public_base_url = "http://test"
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
            # Create a share.
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

            # Anonymous comments disabled by default.
            r_forbidden = await client.post(
                f"/api/v1/public/shares/{share_token}/comments",
                json={"body": "hi"},
            )
            assert r_forbidden.status_code in (401, 403)

            # Enable anonymous comments (captcha required).
            r_cfg = await client.patch(
                f"/api/v1/shares/{share_id}/comment-config",
                headers={"Authorization": "Bearer tok-u1"},
                json={"allow_anonymous_comments": True, "anonymous_comments_require_captcha": True},
            )
            assert r_cfg.status_code == 200

            # Missing captcha -> 400.
            r_missing = await client.post(
                f"/api/v1/public/shares/{share_token}/comments",
                json={"body": "hello"},
            )
            assert r_missing.status_code == 400

            # Upload also requires captcha when configured.
            r_up_missing = await client.post(
                f"/api/v1/public/shares/{share_token}/attachments",
                files={"file": ("hello.txt", b"hello", "text/plain")},
            )
            assert r_up_missing.status_code == 400
            missing_body = cast(dict[str, object], r_up_missing.json())
            assert missing_body.get("error") == "bad_request"
            assert missing_body.get("message") == "captcha required"

            r_up = await client.post(
                f"/api/v1/public/shares/{share_token}/attachments",
                headers={"X-Captcha-Token": "test-pass"},
                files={"file": ("hello.txt", b"hello", "text/plain")},
            )
            assert r_up.status_code == 201
            up_body = cast(dict[str, object], r_up.json())
            attachment_id = cast(str, up_body.get("id"))
            assert attachment_id

            # Uploaded attachment can be downloaded via existing public route.
            r_dl = await client.get(
                f"/api/v1/public/shares/{share_token}/attachments/{attachment_id}"
            )
            assert r_dl.status_code == 200
            assert r_dl.content == b"hello"

            # Captcha bypass token for tests.
            r_ok = await client.post(
                f"/api/v1/public/shares/{share_token}/comments",
                headers={"X-Captcha-Token": "test-pass"},
                json={"body": "hello", "attachment_ids": [attachment_id]},
            )
            assert r_ok.status_code == 201
            c_body = cast(dict[str, object], r_ok.json())
            comment_id = cast(str, c_body.get("id"))
            assert comment_id

            # List comments shows folded state.
            r_list = await client.get(f"/api/v1/public/shares/{share_token}/comments")
            assert r_list.status_code == 200
            list_body = cast(dict[str, object], r_list.json())
            comments = cast(list[object], list_body.get("comments"))
            assert any(
                cast(dict[str, object], c).get("id") == comment_id
                and cast(dict[str, object], c).get("is_folded") is False
                for c in comments
            )

            # Report folds comment.
            r_rep = await client.post(
                f"/api/v1/public/shares/{share_token}/comments/{comment_id}/report"
            )
            assert r_rep.status_code == 200
            rep_body = cast(dict[str, object], r_rep.json())
            assert rep_body.get("is_folded") is True

            r_list2 = await client.get(f"/api/v1/public/shares/{share_token}/comments")
            assert r_list2.status_code == 200
            list2_body = cast(dict[str, object], r_list2.json())
            comments2 = cast(list[object], list2_body.get("comments"))
            assert any(
                cast(dict[str, object], c).get("id") == comment_id
                and cast(dict[str, object], c).get("is_folded") is True
                for c in comments2
            )
    finally:
        settings.database_url = old_db
        settings.attachments_local_dir = old_dir
        settings.share_token_secret = old_secret
        settings.public_base_url = old_public
