from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.models import utc_now
from flow_backend.models_notes import NoteTag, Tag


def _normalize_tag(tag: str) -> tuple[str, str] | None:
    raw = (tag or "").strip()
    if not raw:
        return None
    return raw.lower(), raw


async def _upsert_tags(session: AsyncSession, *, user_id: int, tags: list[str]) -> dict[str, str]:
    """Return mapping name_lower -> tag_id for desired tags."""

    desired: dict[str, str] = {}
    for t in tags:
        norm = _normalize_tag(t)
        if norm is None:
            continue
        lower, original = norm
        desired[lower] = original

    if not desired:
        return {}

    lowers = list(desired.keys())
    stmt = (
        select(Tag)
        .where(Tag.user_id == user_id)
        .where(cast(ColumnElement[object], cast(object, Tag.name_lower)).in_(lowers))
        .where(cast(ColumnElement[object], cast(object, Tag.deleted_at)).is_(None))
    )
    existing = list((await session.exec(stmt)).all())

    by_lower: dict[str, Tag] = {t.name_lower: t for t in existing}
    for lower, original in desired.items():
        if lower in by_lower:
            continue
        tag_row = Tag(
            id=str(uuid.uuid4()),
            user_id=user_id,
            name_original=original,
            name_lower=lower,
        )
        session.add(tag_row)
        by_lower[lower] = tag_row

    await session.flush()
    return {lower: t.id for lower, t in by_lower.items()}


async def set_note_tags(
    session: AsyncSession, *, user_id: int, note_id: str, tags: list[str]
) -> list[str]:
    tag_id_by_lower = await _upsert_tags(session, user_id=user_id, tags=tags)
    desired_tag_ids = set(tag_id_by_lower.values())

    existing_stmt = (
        select(NoteTag).where(NoteTag.user_id == user_id).where(NoteTag.note_id == note_id)
    )
    existing = list((await session.exec(existing_stmt)).all())
    by_tag_id: dict[str, NoteTag] = {nt.tag_id: nt for nt in existing}

    now = utc_now()
    for tag_id in desired_tag_ids:
        nt = by_tag_id.get(tag_id)
        if nt is None:
            nt = NoteTag(
                id=str(uuid.uuid4()),
                user_id=user_id,
                note_id=note_id,
                tag_id=tag_id,
            )
        nt.deleted_at = None
        nt.updated_at = now
        session.add(nt)

    for tag_id, nt in by_tag_id.items():
        if tag_id in desired_tag_ids:
            continue
        if nt.deleted_at is None:
            nt.deleted_at = now
            nt.updated_at = now
            session.add(nt)

    # Prefer input order but de-dup by lower-case.
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        norm = _normalize_tag(t)
        if norm is None:
            continue
        lower, original = norm
        if lower in seen:
            continue
        seen.add(lower)
        out.append(original)
    return out
