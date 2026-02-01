from __future__ import annotations

from collections import defaultdict
from typing import cast

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession as SAAsyncSession
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.config import settings
from flow_backend.models_notes import Note, NoteTag, Tag


def _is_sqlite() -> bool:
    # Use the configured URL as the single source of truth.
    # The runtime engine may be normalized (sqlite+aiosqlite://...), but the prefix remains.
    return settings.database_url.lower().startswith("sqlite")


def _normalize_tag(tag: str | None) -> str | None:
    if tag is None:
        return None
    v = tag.strip()
    if not v:
        return None
    return v.lower()


async def list_note_ids(
    session: AsyncSession,
    *,
    user_id: int,
    tag: str | None,
    include_deleted: bool,
    limit: int,
    offset: int,
) -> tuple[list[str], int]:
    tag_lower = _normalize_tag(tag)

    note_id_col = cast(ColumnElement[object], cast(object, Note.id))

    stmt = select(Note.id).where(Note.user_id == user_id)
    count_stmt = (
        select(sa.func.count(sa.distinct(note_id_col)))
        .select_from(Note)
        .where(Note.user_id == user_id)
    )

    if not include_deleted:
        stmt = stmt.where(cast(ColumnElement[object], cast(object, Note.deleted_at)).is_(None))
        count_stmt = count_stmt.where(
            cast(ColumnElement[object], cast(object, Note.deleted_at)).is_(None)
        )

    if tag_lower is not None:
        # Join through note_tags -> tags, and match tags.name_lower case-insensitively.
        stmt = (
            stmt.join(
                NoteTag,
                cast(ColumnElement[object], cast(object, NoteTag.note_id))
                == cast(ColumnElement[object], cast(object, Note.id)),
            )
            .join(
                Tag,
                cast(ColumnElement[object], cast(object, Tag.id))
                == cast(ColumnElement[object], cast(object, NoteTag.tag_id)),
            )
            .where(Tag.user_id == user_id)
            .where(Tag.name_lower == tag_lower)
            .where(cast(ColumnElement[object], cast(object, NoteTag.deleted_at)).is_(None))
            .where(cast(ColumnElement[object], cast(object, Tag.deleted_at)).is_(None))
        )

        count_stmt = (
            count_stmt.join(
                NoteTag,
                cast(ColumnElement[object], cast(object, NoteTag.note_id))
                == cast(ColumnElement[object], cast(object, Note.id)),
            )
            .join(
                Tag,
                cast(ColumnElement[object], cast(object, Tag.id))
                == cast(ColumnElement[object], cast(object, NoteTag.tag_id)),
            )
            .where(Tag.user_id == user_id)
            .where(Tag.name_lower == tag_lower)
            .where(cast(ColumnElement[object], cast(object, NoteTag.deleted_at)).is_(None))
            .where(cast(ColumnElement[object], cast(object, Tag.deleted_at)).is_(None))
        )

    stmt = (
        stmt.order_by(
            cast(ColumnElement[object], cast(object, Note.updated_at)).desc(),
            cast(ColumnElement[object], cast(object, Note.id)).desc(),
        )
        .limit(limit)
        .offset(offset)
    )

    ids = list((await session.exec(stmt)).all())
    total = int((await session.exec(count_stmt)).first() or 0)
    return ids, total


async def search_note_ids(
    session: AsyncSession,
    *,
    user_id: int,
    q: str | None,
    tag: str | None,
    include_deleted: bool,
    limit: int,
    offset: int,
) -> tuple[list[str], int]:
    query = (q or "").strip()
    if not query:
        return await list_note_ids(
            session,
            user_id=user_id,
            tag=tag,
            include_deleted=include_deleted,
            limit=limit,
            offset=offset,
        )

    if _is_sqlite():
        # SQLite FTS index excludes deleted notes by design; keep behavior consistent.
        return await _search_note_ids_sqlite_fts(
            session,
            user_id=user_id,
            q=query,
            tag=tag,
            limit=limit,
            offset=offset,
        )

    # Non-sqlite fallback: minimal substring search.
    return await _search_note_ids_ilike(
        session,
        user_id=user_id,
        q=query,
        tag=tag,
        include_deleted=include_deleted,
        limit=limit,
        offset=offset,
    )


async def _search_note_ids_sqlite_fts(
    session: AsyncSession,
    *,
    user_id: int,
    q: str,
    tag: str | None,
    limit: int,
    offset: int,
) -> tuple[list[str], int]:
    tag_lower = _normalize_tag(tag)

    tag_join = ""
    tag_where = ""
    params: dict[str, object] = {"user_id": user_id, "q": q, "limit": limit, "offset": offset}
    if tag_lower is not None:
        tag_join = (
            "\nJOIN note_tags nt ON nt.note_id = n.id AND nt.user_id = n.user_id AND nt.deleted_at IS NULL\n"
            "JOIN tags t ON t.id = nt.tag_id AND t.user_id = n.user_id AND t.deleted_at IS NULL\n"
        )
        tag_where = "\n  AND t.name_lower = :tag_lower"
        params["tag_lower"] = tag_lower

    # NOTE: deleted notes are excluded from the FTS index (see migration).
    ids_sql = sa.text(
        """
        SELECT n.id
        FROM notes AS n
        JOIN notes_fts ON notes_fts.note_id = n.id AND notes_fts.user_id = n.user_id
        """
        + tag_join
        + """
        WHERE n.user_id = :user_id
          AND n.deleted_at IS NULL
          AND notes_fts MATCH :q
        """
        + tag_where
        + """
        ORDER BY n.updated_at DESC, n.id DESC
        LIMIT :limit OFFSET :offset
        """
    )

    count_sql = sa.text(
        """
        SELECT COUNT(DISTINCT n.id)
        FROM notes AS n
        JOIN notes_fts ON notes_fts.note_id = n.id AND notes_fts.user_id = n.user_id
        """
        + tag_join
        + """
        WHERE n.user_id = :user_id
          AND n.deleted_at IS NULL
          AND notes_fts MATCH :q
        """
        + tag_where
    )

    sa_session = cast(SAAsyncSession, session)

    ids_result = await sa_session.execute(ids_sql, params)
    ids = [cast(str, x) for x in ids_result.scalars().all()]

    total_result = await sa_session.execute(count_sql, params)
    total = int(total_result.scalar_one() or 0)
    return ids, total


async def _search_note_ids_ilike(
    session: AsyncSession,
    *,
    user_id: int,
    q: str,
    tag: str | None,
    include_deleted: bool,
    limit: int,
    offset: int,
) -> tuple[list[str], int]:
    tag_lower = _normalize_tag(tag)
    pattern = f"%{q}%"

    note_id_col = cast(ColumnElement[object], cast(object, Note.id))
    title_col = cast(ColumnElement[str], cast(object, Note.title))
    body_col = cast(ColumnElement[str], cast(object, Note.body_md))

    stmt = select(Note.id).where(Note.user_id == user_id)
    count_stmt = (
        select(sa.func.count(sa.distinct(note_id_col)))
        .select_from(Note)
        .where(Note.user_id == user_id)
    )

    if not include_deleted:
        stmt = stmt.where(cast(ColumnElement[object], cast(object, Note.deleted_at)).is_(None))
        count_stmt = count_stmt.where(
            cast(ColumnElement[object], cast(object, Note.deleted_at)).is_(None)
        )

    stmt = stmt.where(sa.or_(title_col.ilike(pattern), body_col.ilike(pattern)))
    count_stmt = count_stmt.where(sa.or_(title_col.ilike(pattern), body_col.ilike(pattern)))

    if tag_lower is not None:
        stmt = (
            stmt.join(
                NoteTag,
                cast(ColumnElement[object], cast(object, NoteTag.note_id))
                == cast(ColumnElement[object], cast(object, Note.id)),
            )
            .join(
                Tag,
                cast(ColumnElement[object], cast(object, Tag.id))
                == cast(ColumnElement[object], cast(object, NoteTag.tag_id)),
            )
            .where(Tag.user_id == user_id)
            .where(Tag.name_lower == tag_lower)
            .where(cast(ColumnElement[object], cast(object, NoteTag.deleted_at)).is_(None))
            .where(cast(ColumnElement[object], cast(object, Tag.deleted_at)).is_(None))
        )
        count_stmt = (
            count_stmt.join(
                NoteTag,
                cast(ColumnElement[object], cast(object, NoteTag.note_id))
                == cast(ColumnElement[object], cast(object, Note.id)),
            )
            .join(
                Tag,
                cast(ColumnElement[object], cast(object, Tag.id))
                == cast(ColumnElement[object], cast(object, NoteTag.tag_id)),
            )
            .where(Tag.user_id == user_id)
            .where(Tag.name_lower == tag_lower)
            .where(cast(ColumnElement[object], cast(object, NoteTag.deleted_at)).is_(None))
            .where(cast(ColumnElement[object], cast(object, Tag.deleted_at)).is_(None))
        )

    stmt = (
        stmt.order_by(
            cast(ColumnElement[object], cast(object, Note.updated_at)).desc(),
            cast(ColumnElement[object], cast(object, Note.id)).desc(),
        )
        .limit(limit)
        .offset(offset)
    )

    ids = list((await session.exec(stmt)).all())
    total = int((await session.exec(count_stmt)).first() or 0)
    return ids, total


async def get_notes_by_ids(
    session: AsyncSession,
    *,
    user_id: int,
    note_ids: list[str],
) -> list[Note]:
    if not note_ids:
        return []

    stmt = (
        select(Note)
        .where(Note.user_id == user_id)
        .where(cast(ColumnElement[object], cast(object, Note.id)).in_(note_ids))
        .order_by(
            cast(ColumnElement[object], cast(object, Note.updated_at)).desc(),
            cast(ColumnElement[object], cast(object, Note.id)).desc(),
        )
    )
    return list((await session.exec(stmt)).all())


async def get_tags_for_notes(
    session: AsyncSession,
    *,
    user_id: int,
    note_ids: list[str],
) -> dict[str, list[str]]:
    if not note_ids:
        return {}

    stmt = (
        select(NoteTag.note_id, Tag.name_original)
        .select_from(NoteTag)
        .join(
            Tag,
            cast(ColumnElement[object], cast(object, Tag.id))
            == cast(ColumnElement[object], cast(object, NoteTag.tag_id)),
        )
        .where(NoteTag.user_id == user_id)
        .where(Tag.user_id == user_id)
        .where(cast(ColumnElement[object], cast(object, NoteTag.note_id)).in_(note_ids))
        .where(cast(ColumnElement[object], cast(object, NoteTag.deleted_at)).is_(None))
        .where(cast(ColumnElement[object], cast(object, Tag.deleted_at)).is_(None))
        .order_by(
            cast(ColumnElement[object], cast(object, NoteTag.note_id)).asc(),
            cast(ColumnElement[object], cast(object, Tag.name_lower)).asc(),
        )
    )
    rows = (await session.exec(stmt)).all()

    tags_by_note: dict[str, list[str]] = defaultdict(list)
    for note_id, name_original in rows:
        tags_by_note[str(note_id)].append(str(name_original))
    return dict(tags_by_note)
