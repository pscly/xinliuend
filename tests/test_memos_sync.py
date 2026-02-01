from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlmodel import select

from flow_backend.db import reset_engine_cache, session_scope
from flow_backend.integrations.memos_notes_api import MemosMemo, sha256_hex
from flow_backend.models import SyncEvent, User, utc_now
from flow_backend.models_notes import Note, NoteRemote, NoteRevision
from flow_backend.services import memos_sync_service


def _alembic_upgrade_head() -> None:
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")


@dataclass
class FakeMemosAPI:
    memos: dict[str, MemosMemo]
    updated: list[tuple[str, str]]
    created: list[str]
    deleted: list[str]

    async def list_memos(self) -> list[MemosMemo]:
        return list(self.memos.values())

    async def create_memo(self, *, content: str) -> MemosMemo:
        remote_id = str(len(self.memos) + 1)
        memo = MemosMemo(
            remote_id=f"memos/{remote_id}", content=content, updated_at_ms=1, deleted=False
        )
        self.memos[remote_id] = memo
        self.created.append(remote_id)
        return memo

    async def update_memo(self, *, remote_id: str, content: str) -> MemosMemo:
        rid = remote_id.rsplit("/", 1)[-1]
        memo = MemosMemo(remote_id=f"memos/{rid}", content=content, updated_at_ms=2, deleted=False)
        self.memos[rid] = memo
        self.updated.append((rid, content))
        return memo

    async def delete_memo(self, *, remote_id: str) -> None:
        rid = remote_id.rsplit("/", 1)[-1]
        self.memos.pop(rid, None)
        self.deleted.append(rid)


@pytest.mark.anyio
async def test_memos_sync_creates_local_note_from_remote(tmp_path: Path):
    from flow_backend.config import settings

    old_db = settings.database_url
    try:
        settings.database_url = f"sqlite:///{tmp_path / 'test-memos-sync-1.db'}"
        reset_engine_cache()
        _alembic_upgrade_head()

        async with session_scope() as session:
            user = User(username="u1", password_hash="x", memos_token="tok", is_active=True)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            assert user.id is not None
            user_id = int(user.id)

            api = FakeMemosAPI(
                memos={
                    "1": MemosMemo(
                        remote_id="memos/1", content="hello #work", updated_at_ms=1, deleted=False
                    )
                },
                updated=[],
                created=[],
                deleted=[],
            )

            summary = await memos_sync_service.sync_user_notes(
                session=session,
                user_id=user_id,
                memos_api=api,
            )
            assert summary.created_local == 1

            notes = list((await session.exec(select(Note))).all())
            assert len(notes) == 1
            assert notes[0].body_md == "hello #work"

            remotes = list((await session.exec(select(NoteRemote))).all())
            assert len(remotes) == 1
            assert remotes[0].provider == "memos"
            assert remotes[0].remote_id == "1"
            assert remotes[0].remote_sha256_hex == sha256_hex("hello #work")

            events = list((await session.exec(select(SyncEvent))).all())
            assert len(events) == 1
            assert events[0].resource == "note"
            assert events[0].action == "upsert"
    finally:
        settings.database_url = old_db


@pytest.mark.anyio
async def test_memos_sync_remote_overwrite_creates_conflict_revision(tmp_path: Path):
    from flow_backend.config import settings

    old_db = settings.database_url
    try:
        settings.database_url = f"sqlite:///{tmp_path / 'test-memos-sync-2.db'}"
        reset_engine_cache()
        _alembic_upgrade_head()

        note_id = str(uuid.uuid4())
        async with session_scope() as session:
            user = User(username="u1", password_hash="x", memos_token="tok", is_active=True)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            assert user.id is not None
            user_id = int(user.id)

            note = Note(
                id=note_id,
                user_id=user_id,
                title="t",
                body_md="local",
                client_updated_at_ms=100,
                updated_at=utc_now(),
            )
            session.add(note)
            session.add(
                NoteRemote(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    note_id=note_id,
                    provider="memos",
                    remote_id="1",
                    remote_sha256_hex=sha256_hex("old-remote"),
                )
            )
            await session.commit()

            api = FakeMemosAPI(
                memos={
                    "1": MemosMemo(
                        remote_id="memos/1", content="remote", updated_at_ms=1, deleted=False
                    )
                },
                updated=[],
                created=[],
                deleted=[],
            )

            summary = await memos_sync_service.sync_user_notes(
                session=session, user_id=user_id, memos_api=api
            )
            assert summary.updated_local_from_remote == 1
            assert summary.conflicts == 1

            note2 = (
                await session.exec(
                    select(Note).where(Note.user_id == user_id).where(Note.id == note_id)
                )
            ).first()
            assert note2 is not None
            assert note2.body_md == "remote"

            rev = (
                await session.exec(
                    select(NoteRevision)
                    .where(NoteRevision.user_id == user_id)
                    .where(NoteRevision.note_id == note_id)
                    .where(NoteRevision.kind == "CONFLICT")
                )
            ).first()
            assert rev is not None
            assert rev.reason == "memos_overwrite"
            assert rev.snapshot_json.get("body_md") == "local"
    finally:
        settings.database_url = old_db


@pytest.mark.anyio
async def test_memos_sync_pushes_local_when_remote_unchanged(tmp_path: Path):
    from flow_backend.config import settings

    old_db = settings.database_url
    try:
        settings.database_url = f"sqlite:///{tmp_path / 'test-memos-sync-3.db'}"
        reset_engine_cache()
        _alembic_upgrade_head()

        note_id = str(uuid.uuid4())
        async with session_scope() as session:
            user = User(username="u1", password_hash="x", memos_token="tok", is_active=True)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            assert user.id is not None
            user_id = int(user.id)

            note = Note(
                id=note_id,
                user_id=user_id,
                title="t",
                body_md="local-new",
                client_updated_at_ms=100,
                updated_at=utc_now(),
            )
            session.add(note)
            session.add(
                NoteRemote(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    note_id=note_id,
                    provider="memos",
                    remote_id="1",
                    remote_sha256_hex=sha256_hex("remote-old"),
                )
            )
            await session.commit()

            # Remote is unchanged (still "remote-old"), but local diverged.
            api = FakeMemosAPI(
                memos={
                    "1": MemosMemo(
                        remote_id="memos/1", content="remote-old", updated_at_ms=1, deleted=False
                    )
                },
                updated=[],
                created=[],
                deleted=[],
            )

            summary = await memos_sync_service.sync_user_notes(
                session=session, user_id=user_id, memos_api=api
            )
            assert summary.pushed_local_to_remote == 1
            assert api.updated and api.updated[0][0] == "1"

            nr = (
                await session.exec(
                    select(NoteRemote)
                    .where(NoteRemote.user_id == user_id)
                    .where(NoteRemote.note_id == note_id)
                )
            ).first()
            assert nr is not None
            assert nr.remote_sha256_hex == sha256_hex("local-new")
    finally:
        settings.database_url = old_db


@pytest.mark.anyio
async def test_memos_sync_remote_missing_deletes_local(tmp_path: Path):
    from flow_backend.config import settings

    old_db = settings.database_url
    try:
        settings.database_url = f"sqlite:///{tmp_path / 'test-memos-sync-4.db'}"
        reset_engine_cache()
        _alembic_upgrade_head()

        note_id = str(uuid.uuid4())
        async with session_scope() as session:
            user = User(username="u1", password_hash="x", memos_token="tok", is_active=True)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            assert user.id is not None
            user_id = int(user.id)

            note = Note(
                id=note_id,
                user_id=user_id,
                title="t",
                body_md="local",
                client_updated_at_ms=100,
                updated_at=utc_now(),
            )
            session.add(note)
            session.add(
                NoteRemote(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    note_id=note_id,
                    provider="memos",
                    remote_id="1",
                    remote_sha256_hex=sha256_hex("local"),
                )
            )
            await session.commit()

            api = FakeMemosAPI(memos={}, updated=[], created=[], deleted=[])
            summary = await memos_sync_service.sync_user_notes(
                session=session, user_id=user_id, memos_api=api
            )
            assert summary.deleted_local_from_remote == 1
            assert summary.conflicts == 1

            note2 = (
                await session.exec(
                    select(Note).where(Note.user_id == user_id).where(Note.id == note_id)
                )
            ).first()
            assert note2 is not None
            assert note2.deleted_at is not None

            rev = (
                await session.exec(
                    select(NoteRevision)
                    .where(NoteRevision.user_id == user_id)
                    .where(NoteRevision.note_id == note_id)
                    .where(NoteRevision.kind == "CONFLICT")
                    .where(NoteRevision.reason == "memos_deleted")
                )
            ).first()
            assert rev is not None
    finally:
        settings.database_url = old_db


@pytest.mark.anyio
async def test_memos_sync_creates_remote_for_local_only_note(tmp_path: Path):
    from flow_backend.config import settings

    old_db = settings.database_url
    try:
        settings.database_url = f"sqlite:///{tmp_path / 'test-memos-sync-5.db'}"
        reset_engine_cache()
        _alembic_upgrade_head()

        async with session_scope() as session:
            user = User(username="u1", password_hash="x", memos_token="tok", is_active=True)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            assert user.id is not None
            user_id = int(user.id)

            note = Note(
                id=str(uuid.uuid4()),
                user_id=user_id,
                title="t",
                body_md="local",
                client_updated_at_ms=100,
                updated_at=utc_now(),
            )
            session.add(note)
            await session.commit()

            api = FakeMemosAPI(memos={}, updated=[], created=[], deleted=[])
            summary = await memos_sync_service.sync_user_notes(
                session=session, user_id=user_id, memos_api=api
            )
            assert summary.created_remote_from_local == 1
            assert api.created

            remotes = list((await session.exec(select(NoteRemote))).all())
            assert len(remotes) == 1
            assert remotes[0].note_id == note.id
    finally:
        settings.database_url = old_db
