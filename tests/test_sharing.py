from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import timedelta
from pathlib import Path
from typing import cast

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlmodel import select

from flow_backend.config import settings
from flow_backend.db import reset_engine_cache, session_scope
from flow_backend.main import app  # pyright: ignore[reportMissingTypeStubs]
from flow_backend.models import User, utc_now
from flow_backend.models_notes import Note, NoteShare


def _make_async_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _alembic_upgrade_head() -> None:
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")


def _hmac_hex(secret: str, token: str) -> str:
    return hmac.new(secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


@pytest.mark.anyio
async def test_sharing_lifecycle_and_public_download(tmp_path: Path):
    old_db = settings.database_url
    old_dir = settings.attachments_local_dir
    old_secret = settings.share_token_secret
    old_public = settings.public_base_url
    try:
        settings.database_url = f"sqlite:///{tmp_path / 'test-sharing.db'}"
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
            # Upload an attachment so we can verify public attachment download.
            r_up = await client.post(
                "/api/v2/notes/note-1/attachments",
                headers={"Authorization": "Bearer tok-u1"},
                files={"file": ("hello.txt", b"hello", "text/plain")},
            )
            assert r_up.status_code == 201
            attachment_id = cast(str, cast(dict[str, object], r_up.json()).get("id"))
            assert attachment_id

            # Create a share.
            r = await client.post(
                "/api/v2/notes/note-1/shares",
                headers={"Authorization": "Bearer tok-u1"},
                json={},
            )
            assert r.status_code == 201
            body = cast(dict[str, object], r.json())
            share_id = cast(str, body.get("share_id"))
            share_token = cast(str, body.get("share_token"))
            share_url = cast(str, body.get("share_url"))
            assert share_id
            assert share_token
            assert share_url.endswith(f"/api/v2/public/shares/{share_token}")

            # Ensure plaintext token is not stored; only HMAC is stored.
            async with session_scope() as session:
                row = (
                    await session.exec(select(NoteShare).where(NoteShare.id == share_id))
                ).first()
                assert row is not None
                assert row.token_prefix == share_token[:8]
                assert row.token_hmac_hex == _hmac_hex(settings.share_token_secret, share_token)
                assert row.token_hmac_hex != share_token

            # Public share fetch.
            r_pub = await client.get(f"/api/v2/public/shares/{share_token}")
            assert r_pub.status_code == 200
            pub_body = cast(dict[str, object], r_pub.json())
            note_obj = cast(dict[str, object], pub_body.get("note"))
            assert note_obj.get("id") == "note-1"

            atts = pub_body.get("attachments")
            assert isinstance(atts, list)
            assert any(cast(dict[str, object], a).get("id") == attachment_id for a in atts)

            # Public attachment download.
            r_file = await client.get(
                f"/api/v2/public/shares/{share_token}/attachments/{attachment_id}"
            )
            assert r_file.status_code == 200
            assert r_file.content == b"hello"

            # Revoke and verify public access becomes 404.
            r_del = await client.delete(
                f"/api/v2/shares/{share_id}",
                headers={"Authorization": "Bearer tok-u1"},
            )
            assert r_del.status_code == 204

            r_pub2 = await client.get(f"/api/v2/public/shares/{share_token}")
            assert r_pub2.status_code == 404

        # Expired share returns 410 Gone.
        expired_token = secrets.token_urlsafe(32)
        expired_prefix = expired_token[:8]
        expired_hmac = _hmac_hex(settings.share_token_secret, expired_token)
        async with session_scope() as session:
            session.add(
                NoteShare(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    note_id="note-1",
                    token_prefix=expired_prefix,
                    token_hmac_hex=expired_hmac,
                    expires_at=utc_now() - timedelta(seconds=1),
                )
            )
            await session.commit()

        async with _make_async_client() as client:
            r_exp = await client.get(f"/api/v2/public/shares/{expired_token}")
            assert r_exp.status_code == 410
            exp_body = cast(dict[str, object], r_exp.json())
            assert exp_body.get("error") == "gone"

        # Deleted note should make public share return 404 (not_found).
        token2 = secrets.token_urlsafe(32)
        prefix2 = token2[:8]
        hmac2 = _hmac_hex(settings.share_token_secret, token2)
        share2_id = str(uuid.uuid4())
        async with session_scope() as session:
            session.add(
                NoteShare(
                    id=share2_id,
                    user_id=user_id,
                    note_id="note-1",
                    token_prefix=prefix2,
                    token_hmac_hex=hmac2,
                    expires_at=utc_now() + timedelta(days=1),
                )
            )
            note_row = (
                await session.exec(
                    select(Note).where(Note.id == "note-1").where(Note.user_id == user_id)
                )
            ).first()
            assert note_row is not None
            note_row.deleted_at = utc_now()
            session.add(note_row)
            await session.commit()

        async with _make_async_client() as client:
            r_del_note = await client.get(f"/api/v2/public/shares/{token2}")
            assert r_del_note.status_code == 404
    finally:
        settings.database_url = old_db
        settings.attachments_local_dir = old_dir
        settings.share_token_secret = old_secret
        settings.public_base_url = old_public
