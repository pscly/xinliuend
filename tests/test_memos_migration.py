from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlmodel import select

from flow_backend.config import settings
from flow_backend.db import reset_engine_cache, session_scope
from flow_backend.integrations.memos_notes_api import MemosMemo, sha256_hex
from flow_backend.main import app
from flow_backend.models import User, utc_now
from flow_backend.models_notes import Note, NoteRemote, NoteRevision
from flow_backend.routers.memos_migration import get_memos_notes_api
from flow_backend.services import memos_sync_service


def _alembic_upgrade_head() -> None:
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")


def _make_async_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@dataclass
class FakeMemosAPI:
    memos: dict[str, MemosMemo]

    async def list_memos(self) -> list[MemosMemo]:
        return list(self.memos.values())

    async def create_memo(self, *, content: str) -> MemosMemo:  # noqa: ARG002
        raise AssertionError("pull-only 迁移不应调用 create_memo")

    async def update_memo(self, *, remote_id: str, content: str) -> MemosMemo:  # noqa: ARG002
        raise AssertionError("pull-only 迁移不应调用 update_memo")

    async def delete_memo(self, *, remote_id: str) -> None:  # noqa: ARG002
        raise AssertionError("pull-only 迁移不应调用 delete_memo")


@pytest.mark.anyio
async def test_memos_pull_plan_counts(tmp_path: Path) -> None:
    old_db = settings.database_url
    try:
        settings.database_url = f"sqlite:///{tmp_path / 'test-memos-migration-plan.db'}"
        reset_engine_cache()
        _alembic_upgrade_head()

        async with session_scope() as session:
            user = User(username="u1", password_hash="x", memos_token="tok", is_active=True)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            assert user.id is not None
            user_id = int(user.id)

            # Remote 1: changed; local diverged -> overwrite + conflict.
            note_id_1 = str(uuid.uuid4())
            session.add(
                Note(
                    id=note_id_1,
                    user_id=user_id,
                    title="t1",
                    body_md="local-changed",
                    client_updated_at_ms=100,
                    updated_at=utc_now(),
                )
            )
            session.add(
                NoteRemote(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    note_id=note_id_1,
                    provider="memos",
                    remote_id="1",
                    remote_sha256_hex=sha256_hex("remote-old"),
                )
            )

            # Remote 3: missing -> local deleted + conflict.
            note_id_3 = str(uuid.uuid4())
            session.add(
                Note(
                    id=note_id_3,
                    user_id=user_id,
                    title="t3",
                    body_md="local-3",
                    client_updated_at_ms=100,
                    updated_at=utc_now(),
                )
            )
            session.add(
                NoteRemote(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    note_id=note_id_3,
                    provider="memos",
                    remote_id="3",
                    remote_sha256_hex=sha256_hex("remote-3"),
                )
            )

            # Remote 4: exists; local is deleted -> should restore.
            note_id_4 = str(uuid.uuid4())
            session.add(
                Note(
                    id=note_id_4,
                    user_id=user_id,
                    title="t4",
                    body_md="local-4",
                    client_updated_at_ms=100,
                    updated_at=utc_now(),
                    deleted_at=utc_now(),
                )
            )
            session.add(
                NoteRemote(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    note_id=note_id_4,
                    provider="memos",
                    remote_id="4",
                    remote_sha256_hex=sha256_hex("remote-4"),
                )
            )
            await session.commit()

            api = FakeMemosAPI(
                memos={
                    "1": MemosMemo(
                        remote_id="memos/1", content="remote-new", updated_at_ms=2, deleted=False
                    ),
                    # Remote 2: new -> create local.
                    "2": MemosMemo(
                        remote_id="memos/2", content="remote-2", updated_at_ms=1, deleted=False
                    ),
                    "4": MemosMemo(
                        remote_id="memos/4", content="remote-4", updated_at_ms=1, deleted=False
                    ),
                }
            )

            plan = await memos_sync_service.plan_pull_user_notes(
                session=session, user_id=user_id, memos_api=api
            )
            assert plan.remote_total == 3
            assert plan.created_local == 1
            assert plan.updated_local_from_remote == 2  # remote 1 overwrite + remote 4 restore
            assert plan.deleted_local_from_remote == 1
            assert plan.conflicts == 2  # remote overwrite + remote missing
    finally:
        settings.database_url = old_db


@pytest.mark.anyio
async def test_memos_pull_apply_is_pull_only(tmp_path: Path) -> None:
    old_db = settings.database_url
    try:
        settings.database_url = f"sqlite:///{tmp_path / 'test-memos-migration-apply.db'}"
        reset_engine_cache()
        _alembic_upgrade_head()

        async with session_scope() as session:
            user = User(username="u1", password_hash="x", memos_token="tok", is_active=True)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            assert user.id is not None
            user_id = int(user.id)

            note_id_1 = str(uuid.uuid4())
            session.add(
                Note(
                    id=note_id_1,
                    user_id=user_id,
                    title="t1",
                    body_md="local-changed",
                    client_updated_at_ms=100,
                    updated_at=utc_now(),
                )
            )
            session.add(
                NoteRemote(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    note_id=note_id_1,
                    provider="memos",
                    remote_id="1",
                    remote_sha256_hex=sha256_hex("remote-old"),
                )
            )

            note_id_3 = str(uuid.uuid4())
            session.add(
                Note(
                    id=note_id_3,
                    user_id=user_id,
                    title="t3",
                    body_md="local-3",
                    client_updated_at_ms=100,
                    updated_at=utc_now(),
                )
            )
            session.add(
                NoteRemote(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    note_id=note_id_3,
                    provider="memos",
                    remote_id="3",
                    remote_sha256_hex=sha256_hex("remote-3"),
                )
            )

            note_id_4 = str(uuid.uuid4())
            session.add(
                Note(
                    id=note_id_4,
                    user_id=user_id,
                    title="t4",
                    body_md="local-4",
                    client_updated_at_ms=100,
                    updated_at=utc_now(),
                    deleted_at=utc_now(),
                )
            )
            session.add(
                NoteRemote(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    note_id=note_id_4,
                    provider="memos",
                    remote_id="4",
                    remote_sha256_hex=sha256_hex("remote-4"),
                )
            )
            await session.commit()

            api = FakeMemosAPI(
                memos={
                    "1": MemosMemo(
                        remote_id="memos/1", content="remote-new", updated_at_ms=2, deleted=False
                    ),
                    "2": MemosMemo(
                        remote_id="memos/2", content="remote-2", updated_at_ms=1, deleted=False
                    ),
                    "4": MemosMemo(
                        remote_id="memos/4", content="remote-4", updated_at_ms=1, deleted=False
                    ),
                }
            )

            summary = await memos_sync_service.apply_pull_user_notes(
                session=session, user_id=user_id, memos_api=api
            )
            assert summary.remote_total == 3
            assert summary.created_local == 1
            assert summary.updated_local_from_remote == 2
            assert summary.deleted_local_from_remote == 1
            assert summary.conflicts == 2

            # Note 1 overwritten; conflict revision preserved.
            note1 = (await session.exec(select(Note).where(Note.id == note_id_1))).first()
            assert note1 is not None
            assert note1.body_md == "remote-new"
            rev1 = (
                await session.exec(
                    select(NoteRevision)
                    .where(NoteRevision.note_id == note_id_1)
                    .where(NoteRevision.kind == "CONFLICT")
                )
            ).first()
            assert rev1 is not None
            assert rev1.reason == "memos_overwrite"
            assert rev1.snapshot_json.get("body_md") == "local-changed"

            # Note 3 deleted (remote missing); conflict revision preserved.
            note3 = (await session.exec(select(Note).where(Note.id == note_id_3))).first()
            assert note3 is not None
            assert note3.deleted_at is not None
            rev3 = (
                await session.exec(
                    select(NoteRevision)
                    .where(NoteRevision.note_id == note_id_3)
                    .where(NoteRevision.kind == "CONFLICT")
                )
            ).first()
            assert rev3 is not None
            assert rev3.reason == "memos_deleted"

            # Note 4 restored.
            note4 = (await session.exec(select(Note).where(Note.id == note_id_4))).first()
            assert note4 is not None
            assert note4.deleted_at is None
            assert note4.body_md == "remote-4"
    finally:
        settings.database_url = old_db


@pytest.mark.anyio
async def test_memos_migration_router_preview_and_apply(tmp_path: Path) -> None:
    old_db = settings.database_url
    try:
        settings.database_url = f"sqlite:///{tmp_path / 'test-memos-migration-router.db'}"
        reset_engine_cache()
        _alembic_upgrade_head()

        api = FakeMemosAPI(
            memos={
                "1": MemosMemo(remote_id="memos/1", content="hello", updated_at_ms=1, deleted=False)
            }
        )

        async with session_scope() as session:
            user = User(username="u1", password_hash="x", memos_token="tok", is_active=True)
            session.add(user)
            await session.commit()

        async def _override_memos_api() -> FakeMemosAPI:
            return api

        app.dependency_overrides[get_memos_notes_api] = _override_memos_api
        try:
            async with _make_async_client() as client:
                r1 = await client.post(
                    "/api/v1/memos/migration/preview",
                    headers={"Authorization": "Bearer tok"},
                )
                assert r1.status_code == 200
                data1 = r1.json()
                assert data1["kind"] == "preview"
                assert data1["summary"]["created_local"] == 1

                r2 = await client.post(
                    "/api/v1/memos/migration/apply",
                    headers={"Authorization": "Bearer tok"},
                )
                assert r2.status_code == 200
                data2 = r2.json()
                assert data2["kind"] == "apply"
                assert data2["summary"]["created_local"] == 1
        finally:
            app.dependency_overrides.pop(get_memos_notes_api, None)
    finally:
        settings.database_url = old_db
