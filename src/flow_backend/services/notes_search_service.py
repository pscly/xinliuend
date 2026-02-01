from __future__ import annotations

from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.models_notes import Note
from flow_backend.repositories import notes_search_repo


async def list_notes(
    *,
    session: AsyncSession,
    user_id: int,
    limit: int,
    offset: int,
    tag: str | None,
    q: str | None,
    include_deleted: bool,
) -> tuple[list[Note], dict[str, list[str]], int]:
    note_ids, total = await notes_search_repo.search_note_ids(
        session,
        user_id=user_id,
        q=q,
        tag=tag,
        include_deleted=include_deleted,
        limit=limit,
        offset=offset,
    )

    notes = await notes_search_repo.get_notes_by_ids(session, user_id=user_id, note_ids=note_ids)
    tags_by_note_id = await notes_search_repo.get_tags_for_notes(
        session, user_id=user_id, note_ids=[n.id for n in notes]
    )
    return notes, tags_by_note_id, total
