from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.integrations.memos_notes_api import (
    MemosMemo,
    MemosNotesAPI,
    memo_id_from_remote_id,
    sha256_hex,
)
from flow_backend.models import SyncEvent, utc_now
from flow_backend.models_notes import Note, NoteRemote, NoteRevision
from flow_backend.repositories import note_revisions_repo
from flow_backend.services.notes_tags_service import set_note_tags
from flow_backend.sync_utils import now_ms


_HASHTAG_RE = re.compile(r"(?<!\S)#([^\s#]+)")


def _derive_title_from_body(body_md: str) -> str:
    for line in (body_md or "").splitlines():
        line = line.strip()
        if line:
            return line[:500]
    return ""


def _extract_hashtags(content: str) -> list[str]:
    # Memos tags are usually '#tag' without a space, while Markdown headings are '# Title'.
    out: list[str] = []
    seen: set[str] = set()
    for m in _HASHTAG_RE.finditer(content or ""):
        raw = (m.group(1) or "").strip().strip('.,;:()[]{}"')
        if not raw:
            continue
        key = raw.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(raw)
    return out


def _record_sync_event(session: AsyncSession, *, user_id: int, entity_id: str, action: str) -> None:
    session.add(
        SyncEvent(
            user_id=user_id,
            resource="note",
            entity_id=entity_id,
            action=action,
            created_at=utc_now(),
        )
    )


def _snapshot_note(*, note: Note, tags: list[str]) -> dict[str, Any]:
    return {
        "title": note.title,
        "body_md": note.body_md,
        "tags": tags,
        "client_updated_at_ms": note.client_updated_at_ms,
    }


@dataclass(frozen=True)
class MemosSyncSummary:
    created_local: int
    updated_local_from_remote: int
    deleted_local_from_remote: int
    pushed_local_to_remote: int
    created_remote_from_local: int
    conflicts: int


@dataclass(frozen=True)
class MemosPullSummary:
    remote_total: int
    created_local: int
    updated_local_from_remote: int
    deleted_local_from_remote: int
    conflicts: int


async def sync_user_notes(
    *,
    session: AsyncSession,
    user_id: int,
    memos_api: MemosNotesAPI,
) -> MemosSyncSummary:
    """Bidirectional sync between local notes and Memos.

    Memos is authoritative: when both sides diverged, remote wins and local changes
    are preserved as CONFLICT revisions.

    This function is safe to run multiple times (idempotent on equal content).
    """

    created_local = 0
    updated_local_from_remote = 0
    deleted_local_from_remote = 0
    pushed_local_to_remote = 0
    created_remote_from_local = 0
    conflicts = 0

    remote_memos = await memos_api.list_memos()
    # Normalize remote ids into a stable numeric key.
    remote_by_id: dict[str, MemosMemo] = {}
    for m in remote_memos:
        try:
            rid = memo_id_from_remote_id(m.remote_id)
        except Exception:
            continue
        remote_by_id[rid] = m

    remotes_stmt = (
        select(NoteRemote)
        .where(NoteRemote.user_id == user_id)
        .where(NoteRemote.provider == "memos")
        .where(cast(ColumnElement[object], cast(object, NoteRemote.deleted_at)).is_(None))
    )
    note_remotes = list((await session.exec(remotes_stmt)).all())
    remote_map: dict[str, NoteRemote] = {nr.remote_id: nr for nr in note_remotes}

    async def _apply_all() -> None:
        nonlocal created_local
        nonlocal updated_local_from_remote
        nonlocal deleted_local_from_remote
        nonlocal pushed_local_to_remote
        nonlocal created_remote_from_local
        nonlocal conflicts

        # 1) Remote -> local: create/update/delete.
        for remote_id, memo in remote_by_id.items():
            if memo.deleted:
                continue
            remote_hash = sha256_hex(memo.content)
            nr = remote_map.get(remote_id)
            if nr is None:
                # New remote memo -> create local note.
                note_id = str(uuid.uuid4())
                tags = _extract_hashtags(memo.content)
                note = Note(
                    id=note_id,
                    user_id=user_id,
                    title=_derive_title_from_body(memo.content),
                    body_md=memo.content,
                    client_updated_at_ms=now_ms(),
                    updated_at=utc_now(),
                )
                session.add(note)
                await session.flush()
                await set_note_tags(session, user_id=user_id, note_id=note_id, tags=tags)

                nr = NoteRemote(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    note_id=note_id,
                    provider="memos",
                    remote_id=remote_id,
                    remote_sha256_hex=remote_hash,
                    client_updated_at_ms=int(memo.updated_at_ms or 0),
                )
                session.add(nr)
                _record_sync_event(session, user_id=user_id, entity_id=note_id, action="upsert")
                created_local += 1
                remote_map[remote_id] = nr
                continue

            note = await session.get(Note, nr.note_id)
            if note is None:
                continue

            local_deleted = note.deleted_at is not None
            local_hash = sha256_hex(note.body_md)
            last_remote_hash = nr.remote_sha256_hex

            remote_changed_since_last = (
                last_remote_hash is not None and last_remote_hash != remote_hash
            )
            local_changed_since_last = (
                last_remote_hash is not None and local_hash != last_remote_hash
            )

            if remote_changed_since_last:
                # Remote changed. If local also diverged, preserve local as a conflict revision.
                if local_hash != remote_hash and not local_deleted:
                    tags = await note_revisions_repo.list_note_tags(
                        session, user_id=user_id, note_id=note.id
                    )
                    session.add(
                        NoteRevision(
                            id=str(uuid.uuid4()),
                            user_id=user_id,
                            note_id=note.id,
                            kind="CONFLICT",
                            reason="memos_overwrite",
                            snapshot_json=_snapshot_note(note=note, tags=tags),
                            client_updated_at_ms=now_ms(),
                            updated_at=utc_now(),
                            created_at=utc_now(),
                        )
                    )
                    conflicts += 1

                # Apply remote to local.
                note.body_md = memo.content
                note.title = _derive_title_from_body(memo.content)
                note.deleted_at = None
                note.client_updated_at_ms = now_ms()
                note.updated_at = utc_now()
                session.add(note)
                tags2 = _extract_hashtags(memo.content)
                await set_note_tags(session, user_id=user_id, note_id=note.id, tags=tags2)

                nr.remote_sha256_hex = remote_hash
                nr.client_updated_at_ms = int(memo.updated_at_ms or 0)
                nr.updated_at = utc_now()
                session.add(nr)

                _record_sync_event(session, user_id=user_id, entity_id=note.id, action="upsert")
                updated_local_from_remote += 1
                continue

            # Remote unchanged since last sync.
            if local_deleted:
                # If local was deleted and remote hasn't changed since last sync, propagate delete.
                # Otherwise, we leave it to remote (authoritative) on the next pull.
                if last_remote_hash is not None:
                    await memos_api.delete_memo(remote_id=remote_id)
                    nr.deleted_at = utc_now()
                    nr.updated_at = utc_now()
                    session.add(nr)
                continue

            if local_changed_since_last and local_hash != remote_hash:
                # Local changed (relative to last synced remote), remote unchanged.
                updated = await memos_api.update_memo(remote_id=remote_id, content=note.body_md)
                nr.remote_sha256_hex = sha256_hex(updated.content)
                nr.client_updated_at_ms = int(updated.updated_at_ms or 0)
                nr.updated_at = utc_now()
                session.add(nr)
                pushed_local_to_remote += 1
                continue

            # Keep mapping fresh.
            nr.remote_sha256_hex = remote_hash
            nr.client_updated_at_ms = int(memo.updated_at_ms or 0)
            nr.updated_at = utc_now()
            session.add(nr)

        # 2) Remote deletions (missing remote).
        for remote_id, nr in list(remote_map.items()):
            if remote_id in remote_by_id:
                continue
            note = await session.get(Note, nr.note_id)
            if note is None:
                continue
            if note.deleted_at is not None:
                continue

            tags = await note_revisions_repo.list_note_tags(
                session, user_id=user_id, note_id=note.id
            )
            session.add(
                NoteRevision(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    note_id=note.id,
                    kind="CONFLICT",
                    reason="memos_deleted",
                    snapshot_json=_snapshot_note(note=note, tags=tags),
                    client_updated_at_ms=now_ms(),
                    updated_at=utc_now(),
                    created_at=utc_now(),
                )
            )
            conflicts += 1

            note.deleted_at = utc_now()
            note.client_updated_at_ms = now_ms()
            note.updated_at = utc_now()
            session.add(note)
            nr.deleted_at = utc_now()
            nr.updated_at = utc_now()
            session.add(nr)
            _record_sync_event(session, user_id=user_id, entity_id=note.id, action="delete")
            deleted_local_from_remote += 1

        # 3) Local-only notes -> remote.
        # Fetch all active notes and create remotes for those without a memos mapping.
        notes_stmt = (
            select(Note)
            .where(Note.user_id == user_id)
            .where(cast(ColumnElement[object], cast(object, Note.deleted_at)).is_(None))
        )
        notes = list((await session.exec(notes_stmt)).all())
        have_remote_note_ids = {nr.note_id for nr in remote_map.values()}
        for note in notes:
            if note.id in have_remote_note_ids:
                continue
            created = await memos_api.create_memo(content=note.body_md)
            remote_id = memo_id_from_remote_id(created.remote_id)
            nr = NoteRemote(
                id=str(uuid.uuid4()),
                user_id=user_id,
                note_id=note.id,
                provider="memos",
                remote_id=remote_id,
                remote_sha256_hex=sha256_hex(created.content),
                client_updated_at_ms=int(created.updated_at_ms or 0),
            )
            session.add(nr)
            remote_map[remote_id] = nr
            created_remote_from_local += 1

    if session.in_transaction():
        await _apply_all()
        await session.commit()
    else:
        async with session.begin():
            await _apply_all()

    return MemosSyncSummary(
        created_local=created_local,
        updated_local_from_remote=updated_local_from_remote,
        deleted_local_from_remote=deleted_local_from_remote,
        pushed_local_to_remote=pushed_local_to_remote,
        created_remote_from_local=created_remote_from_local,
        conflicts=conflicts,
    )


def _normalize_remote_memos(remote_memos: list[MemosMemo]) -> dict[str, MemosMemo]:
    remote_by_id: dict[str, MemosMemo] = {}
    for m in remote_memos:
        try:
            rid = memo_id_from_remote_id(m.remote_id)
        except Exception:
            continue
        remote_by_id[rid] = m
    return remote_by_id


async def plan_pull_user_notes(
    *,
    session: AsyncSession,
    user_id: int,
    memos_api: MemosNotesAPI,
) -> MemosPullSummary:
    """Plan a pull-only migration from Memos to local notes.

    Behavior:
    - Only remote -> local create/update/delete.
    - Never writes to Memos.
    - Remote is authoritative for overwrites; local divergence is preserved as CONFLICT revisions
      (counted here, but not created in plan).
    """

    created_local = 0
    updated_local_from_remote = 0
    deleted_local_from_remote = 0
    conflicts = 0

    remote_memos = await memos_api.list_memos()
    remote_by_id = _normalize_remote_memos(remote_memos)

    remotes_stmt = (
        select(NoteRemote)
        .where(NoteRemote.user_id == user_id)
        .where(NoteRemote.provider == "memos")
        .where(cast(ColumnElement[object], cast(object, NoteRemote.deleted_at)).is_(None))
    )
    note_remotes = list((await session.exec(remotes_stmt)).all())
    remote_map: dict[str, NoteRemote] = {nr.remote_id: nr for nr in note_remotes}

    # 1) Remote -> local: create/update/restore.
    for remote_id, memo in remote_by_id.items():
        if memo.deleted:
            continue
        remote_hash = sha256_hex(memo.content)

        nr = remote_map.get(remote_id)
        if nr is None:
            created_local += 1
            continue

        note = await session.get(Note, nr.note_id)
        if note is None:
            continue

        local_deleted = note.deleted_at is not None
        if local_deleted:
            # Pull-only: remote still exists -> restore local.
            updated_local_from_remote += 1
            continue

        local_hash = sha256_hex(note.body_md)
        last_remote_hash = nr.remote_sha256_hex

        remote_changed_since_last = last_remote_hash is not None and last_remote_hash != remote_hash
        local_changed_since_last = last_remote_hash is not None and local_hash != last_remote_hash

        if remote_changed_since_last:
            if local_changed_since_last:
                conflicts += 1
            updated_local_from_remote += 1

    # 2) Remote deletions (missing remote).
    for remote_id, nr in remote_map.items():
        if remote_id in remote_by_id:
            continue
        note = await session.get(Note, nr.note_id)
        if note is None:
            continue
        if note.deleted_at is not None:
            continue
        deleted_local_from_remote += 1
        conflicts += 1

    return MemosPullSummary(
        remote_total=len(remote_by_id),
        created_local=created_local,
        updated_local_from_remote=updated_local_from_remote,
        deleted_local_from_remote=deleted_local_from_remote,
        conflicts=conflicts,
    )


async def apply_pull_user_notes(
    *,
    session: AsyncSession,
    user_id: int,
    memos_api: MemosNotesAPI,
) -> MemosPullSummary:
    """Execute a pull-only migration from Memos to local notes.

    Unlike sync_user_notes(), this function never pushes local changes to Memos.
    """

    created_local = 0
    updated_local_from_remote = 0
    deleted_local_from_remote = 0
    conflicts = 0

    remote_memos = await memos_api.list_memos()
    remote_by_id = _normalize_remote_memos(remote_memos)

    remotes_stmt = (
        select(NoteRemote)
        .where(NoteRemote.user_id == user_id)
        .where(NoteRemote.provider == "memos")
        .where(cast(ColumnElement[object], cast(object, NoteRemote.deleted_at)).is_(None))
    )
    note_remotes = list((await session.exec(remotes_stmt)).all())
    remote_map: dict[str, NoteRemote] = {nr.remote_id: nr for nr in note_remotes}

    async def _apply_all() -> None:
        nonlocal created_local
        nonlocal updated_local_from_remote
        nonlocal deleted_local_from_remote
        nonlocal conflicts

        # 1) Remote -> local: create/update/restore.
        for remote_id, memo in remote_by_id.items():
            if memo.deleted:
                continue

            remote_hash = sha256_hex(memo.content)
            nr = remote_map.get(remote_id)
            if nr is None:
                note_id = str(uuid.uuid4())
                tags = _extract_hashtags(memo.content)
                note = Note(
                    id=note_id,
                    user_id=user_id,
                    title=_derive_title_from_body(memo.content),
                    body_md=memo.content,
                    client_updated_at_ms=now_ms(),
                    updated_at=utc_now(),
                )
                session.add(note)
                await session.flush()
                await set_note_tags(session, user_id=user_id, note_id=note_id, tags=tags)

                nr = NoteRemote(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    note_id=note_id,
                    provider="memos",
                    remote_id=remote_id,
                    remote_sha256_hex=remote_hash,
                    client_updated_at_ms=int(memo.updated_at_ms or 0),
                )
                session.add(nr)
                remote_map[remote_id] = nr
                _record_sync_event(session, user_id=user_id, entity_id=note_id, action="upsert")
                created_local += 1
                continue

            note = await session.get(Note, nr.note_id)
            if note is None:
                continue

            local_deleted = note.deleted_at is not None
            local_hash = sha256_hex(note.body_md)
            last_remote_hash = nr.remote_sha256_hex

            remote_changed_since_last = last_remote_hash is not None and last_remote_hash != remote_hash
            local_changed_since_last = last_remote_hash is not None and local_hash != last_remote_hash

            should_apply_remote = local_deleted or remote_changed_since_last
            if should_apply_remote:
                if remote_changed_since_last and local_changed_since_last and not local_deleted:
                    tags = await note_revisions_repo.list_note_tags(
                        session, user_id=user_id, note_id=note.id
                    )
                    session.add(
                        NoteRevision(
                            id=str(uuid.uuid4()),
                            user_id=user_id,
                            note_id=note.id,
                            kind="CONFLICT",
                            reason="memos_overwrite",
                            snapshot_json=_snapshot_note(note=note, tags=tags),
                            client_updated_at_ms=now_ms(),
                            updated_at=utc_now(),
                            created_at=utc_now(),
                        )
                    )
                    conflicts += 1

                note.body_md = memo.content
                note.title = _derive_title_from_body(memo.content)
                note.deleted_at = None
                note.client_updated_at_ms = now_ms()
                note.updated_at = utc_now()
                session.add(note)
                tags2 = _extract_hashtags(memo.content)
                await set_note_tags(session, user_id=user_id, note_id=note.id, tags=tags2)

                nr.remote_sha256_hex = remote_hash
                nr.client_updated_at_ms = int(memo.updated_at_ms or 0)
                nr.updated_at = utc_now()
                session.add(nr)

                _record_sync_event(session, user_id=user_id, entity_id=note.id, action="upsert")
                updated_local_from_remote += 1
                continue

            # Pull-only: keep mapping fresh even if no local change is applied.
            nr.remote_sha256_hex = remote_hash
            nr.client_updated_at_ms = int(memo.updated_at_ms or 0)
            nr.updated_at = utc_now()
            session.add(nr)

        # 2) Remote deletions (missing remote).
        for remote_id, nr in list(remote_map.items()):
            if remote_id in remote_by_id:
                continue

            note = await session.get(Note, nr.note_id)
            if note is None:
                continue
            if note.deleted_at is not None:
                continue

            tags = await note_revisions_repo.list_note_tags(
                session, user_id=user_id, note_id=note.id
            )
            session.add(
                NoteRevision(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    note_id=note.id,
                    kind="CONFLICT",
                    reason="memos_deleted",
                    snapshot_json=_snapshot_note(note=note, tags=tags),
                    client_updated_at_ms=now_ms(),
                    updated_at=utc_now(),
                    created_at=utc_now(),
                )
            )
            conflicts += 1

            note.deleted_at = utc_now()
            note.client_updated_at_ms = now_ms()
            note.updated_at = utc_now()
            session.add(note)

            nr.deleted_at = utc_now()
            nr.updated_at = utc_now()
            session.add(nr)

            _record_sync_event(session, user_id=user_id, entity_id=note.id, action="delete")
            deleted_local_from_remote += 1

    if session.in_transaction():
        await _apply_all()
        await session.commit()
    else:
        async with session.begin():
            await _apply_all()

    return MemosPullSummary(
        remote_total=len(remote_by_id),
        created_local=created_local,
        updated_local_from_remote=updated_local_from_remote,
        deleted_local_from_remote=deleted_local_from_remote,
        conflicts=conflicts,
    )
