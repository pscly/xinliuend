# pyright: reportArgumentType=false

from __future__ import annotations

from typing import Any, cast

from sqlmodel.ext.asyncio.session import AsyncSession

from flow_backend.config import settings
from flow_backend.domain.sync_planner import (
    ApplyDelete,
    ApplyUpsert,
    ServerRowSnapshot,
    normalize_note_payload,
    normalize_todo_item_payload,
    plan_mutation,
    validate_payload_for_resource,
)
from flow_backend.models import SyncEvent, TodoItem, utc_now
from flow_backend.models_notes import Note
from flow_backend.repositories import note_revisions_repo, v2_sync_repo
from flow_backend.services.notes_tags_service import set_note_tags


def _parse_int(value: object | None) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _note_server_snapshot(note: Note, tags: list[str]) -> ServerRowSnapshot:
    return ServerRowSnapshot(
        entity_id=note.id,
        client_updated_at_ms=_parse_int(note.client_updated_at_ms),
        deleted=note.deleted_at is not None,
        server={
            "id": note.id,
            "title": note.title,
            "body_md": note.body_md,
            "tags": tags,
            "client_updated_at_ms": note.client_updated_at_ms,
            "updated_at": note.updated_at,
            "deleted_at": note.deleted_at,
        },
    )


def _todo_server_snapshot(item: TodoItem) -> ServerRowSnapshot:
    return ServerRowSnapshot(
        entity_id=item.id,
        client_updated_at_ms=_parse_int(item.client_updated_at_ms),
        deleted=item.deleted_at is not None,
        server={
            "id": item.id,
            "list_id": item.list_id,
            "title": item.title,
            "tags": item.tags_json,
            "tzid": item.tzid,
            "client_updated_at_ms": item.client_updated_at_ms,
            "updated_at": item.updated_at,
            "deleted_at": item.deleted_at,
        },
    )


def _record_sync_event(
    session: AsyncSession, *, user_id: int, resource: str, entity_id: str, action: str
) -> None:
    session.add(
        SyncEvent(
            user_id=user_id,
            resource=resource,
            entity_id=entity_id,
            action=action,
            created_at=utc_now(),
        )
    )


async def push(
    *,
    session: AsyncSession,
    user_id: int,
    mutations: list[dict[str, object]],
) -> dict[str, Any]:
    applied: list[dict[str, str]] = []
    rejected: list[dict[str, object]] = []

    async def _apply_all() -> None:
        for raw in mutations:
            resource = str(raw.get("resource") or "")
            entity_id = str(raw.get("entity_id") or "")
            op = str(raw.get("op") or "")
            incoming_ms = _parse_int(raw.get("client_updated_at_ms"))
            data = cast(dict[str, object] | None, raw.get("data"))

            if resource not in {"note", "todo_item"}:
                rejected.append(
                    {"resource": resource, "entity_id": entity_id, "reason": "invalid resource"}
                )
                continue
            if op not in {"upsert", "delete"}:
                rejected.append(
                    {"resource": resource, "entity_id": entity_id, "reason": "invalid op"}
                )
                continue
            if not entity_id:
                rejected.append(
                    {"resource": resource, "entity_id": entity_id, "reason": "missing entity_id"}
                )
                continue

            if resource == "note":
                server_note = await v2_sync_repo.get_note(
                    session, user_id=user_id, note_id=entity_id, include_deleted=True
                )
                server_row = None
                if server_note is not None:
                    server_tags = await note_revisions_repo.list_note_tags(
                        session, user_id=user_id, note_id=entity_id
                    )
                    server_row = _note_server_snapshot(server_note, server_tags)

                if op == "upsert":
                    normalized = normalize_note_payload(dict(data or {}))
                    reason = validate_payload_for_resource(
                        "note", normalized, server_row=server_row
                    )
                    if reason is not None:
                        rejected.append(
                            {"resource": resource, "entity_id": entity_id, "reason": reason}
                        )
                        continue
                else:
                    normalized = None

                plan = plan_mutation(
                    resource="note",
                    entity_id=entity_id,
                    op=cast(Any, op),
                    incoming_client_updated_at_ms=incoming_ms,
                    incoming_payload=normalized,
                    server_row=server_row,
                )

                if plan.reject is not None:
                    rejected.append(
                        {
                            "resource": resource,
                            "entity_id": entity_id,
                            "reason": plan.reject.reason,
                            "server": plan.reject.server,
                        }
                    )
                    continue

                if plan.apply is None:
                    rejected.append(
                        {"resource": resource, "entity_id": entity_id, "reason": "invalid plan"}
                    )
                    continue

                if isinstance(plan.apply, ApplyDelete):
                    note = server_note
                    if note is None:
                        # Idempotent delete.
                        applied.append({"resource": resource, "entity_id": entity_id})
                        continue

                    note.deleted_at = utc_now()
                    note.updated_at = utc_now()
                    note.client_updated_at_ms = plan.apply.client_updated_at_ms
                    session.add(note)
                    _record_sync_event(
                        session,
                        user_id=user_id,
                        resource="note",
                        entity_id=entity_id,
                        action="delete",
                    )
                    applied.append({"resource": resource, "entity_id": entity_id})
                    continue

                if isinstance(plan.apply, ApplyUpsert):
                    payload2 = normalize_note_payload(cast(dict[str, object], plan.apply.data))
                    note = server_note
                    if note is None:
                        # Create.
                        body_obj = payload2.get("body_md")
                        if body_obj is None:
                            rejected.append(
                                {
                                    "resource": resource,
                                    "entity_id": entity_id,
                                    "reason": "missing body_md",
                                }
                            )
                            continue
                        note = Note(
                            id=entity_id,
                            user_id=user_id,
                            title=str(payload2.get("title") or ""),
                            body_md=str(body_obj),
                            client_updated_at_ms=plan.apply.client_updated_at_ms,
                            updated_at=utc_now(),
                        )
                    else:
                        # Update; allow partial payload.
                        if "title" in payload2:
                            note.title = str(payload2.get("title") or "")
                        if "body_md" in payload2:
                            note.body_md = str(payload2.get("body_md") or "")
                        note.client_updated_at_ms = plan.apply.client_updated_at_ms
                        note.updated_at = utc_now()
                        note.deleted_at = None

                    session.add(note)
                    tags_in = cast(list[str], payload2.get("tags") or [])
                    await set_note_tags(session, user_id=user_id, note_id=note.id, tags=tags_in)
                    _record_sync_event(
                        session,
                        user_id=user_id,
                        resource="note",
                        entity_id=entity_id,
                        action="upsert",
                    )
                    applied.append({"resource": resource, "entity_id": entity_id})
                    continue

            # todo_item
            server_item = await v2_sync_repo.get_todo_item(
                session, user_id=user_id, item_id=entity_id, include_deleted=True
            )
            server_row2 = _todo_server_snapshot(server_item) if server_item is not None else None

            if op == "upsert":
                normalized2 = normalize_todo_item_payload(dict(data or {}))
                reason2 = validate_payload_for_resource(
                    "todo_item", normalized2, server_row=server_row2
                )
                if reason2 is not None:
                    rejected.append(
                        {"resource": resource, "entity_id": entity_id, "reason": reason2}
                    )
                    continue
            else:
                normalized2 = None

            plan2 = plan_mutation(
                resource="todo_item",
                entity_id=entity_id,
                op=cast(Any, op),
                incoming_client_updated_at_ms=incoming_ms,
                incoming_payload=normalized2,
                server_row=server_row2,
            )

            if plan2.reject is not None:
                rejected.append(
                    {
                        "resource": resource,
                        "entity_id": entity_id,
                        "reason": plan2.reject.reason,
                        "server": plan2.reject.server,
                    }
                )
                continue

            if plan2.apply is None:
                rejected.append(
                    {"resource": resource, "entity_id": entity_id, "reason": "invalid plan"}
                )
                continue

            if isinstance(plan2.apply, ApplyDelete):
                item = server_item
                if item is None:
                    applied.append({"resource": resource, "entity_id": entity_id})
                    continue
                item.deleted_at = utc_now()
                item.updated_at = utc_now()
                item.client_updated_at_ms = plan2.apply.client_updated_at_ms
                session.add(item)
                _record_sync_event(
                    session,
                    user_id=user_id,
                    resource="todo_item",
                    entity_id=entity_id,
                    action="delete",
                )
                applied.append({"resource": resource, "entity_id": entity_id})
                continue

            if isinstance(plan2.apply, ApplyUpsert):
                payload3 = normalize_todo_item_payload(cast(dict[str, object], plan2.apply.data))
                item = server_item
                if item is None:
                    list_id = str(payload3.get("list_id") or "").strip()
                    if not list_id:
                        rejected.append(
                            {
                                "resource": resource,
                                "entity_id": entity_id,
                                "reason": "missing list_id",
                            }
                        )
                        continue

                    tzid_in = str(payload3.get("tzid") or "").strip()
                    tzid = tzid_in or settings.default_tzid
                    tags_in = cast(list[str], payload3.get("tags") or [])
                    item = TodoItem(
                        id=entity_id,
                        user_id=user_id,
                        list_id=list_id,
                        title=str(payload3.get("title") or "tmp"),
                        tags_json=tags_in,
                        tzid=tzid,
                        client_updated_at_ms=plan2.apply.client_updated_at_ms,
                        updated_at=utc_now(),
                    )
                else:
                    if "title" in payload3:
                        item.title = str(payload3.get("title") or item.title)
                    if "list_id" in payload3:
                        item.list_id = str(payload3.get("list_id") or item.list_id)
                    item.tags_json = cast(list[str], payload3.get("tags") or item.tags_json)
                    if "tzid" in payload3:
                        item.tzid = str(payload3.get("tzid") or "").strip() or settings.default_tzid
                    item.client_updated_at_ms = plan2.apply.client_updated_at_ms
                    item.updated_at = utc_now()
                    item.deleted_at = None

                session.add(item)
                _record_sync_event(
                    session,
                    user_id=user_id,
                    resource="todo_item",
                    entity_id=entity_id,
                    action="upsert",
                )
                applied.append({"resource": resource, "entity_id": entity_id})
                continue

    try:
        if session.in_transaction():
            await _apply_all()
            await session.commit()
        else:
            async with session.begin():
                await _apply_all()
    except Exception:
        try:
            await session.rollback()
        except Exception:
            pass
        raise

    cursor = await v2_sync_repo.get_latest_cursor(session, user_id=user_id)
    return {
        "cursor": cursor,
        "applied": applied,
        "rejected": rejected,
    }


async def pull(
    *,
    session: AsyncSession,
    user_id: int,
    cursor: int,
    limit: int,
) -> dict[str, Any]:
    events, has_more = await v2_sync_repo.list_sync_events(
        session, user_id=user_id, cursor=cursor, limit=limit
    )
    next_cursor = cursor
    note_ids: set[str] = set()
    todo_ids: set[str] = set()
    for e in events:
        next_cursor = max(next_cursor, _parse_int(e.id))
        if e.resource == "note":
            note_ids.add(e.entity_id)
        if e.resource == "todo_item":
            todo_ids.add(e.entity_id)

    notes: list[dict[str, object]] = []
    for nid in sorted(note_ids):
        n = await v2_sync_repo.get_note(session, user_id=user_id, note_id=nid, include_deleted=True)
        if n is None:
            continue
        tags = await note_revisions_repo.list_note_tags(session, user_id=user_id, note_id=nid)
        notes.append(
            {
                "id": n.id,
                "title": n.title,
                "body_md": n.body_md,
                "tags": tags,
                "client_updated_at_ms": n.client_updated_at_ms,
                "created_at": n.created_at,
                "updated_at": n.updated_at,
                "deleted_at": n.deleted_at,
            }
        )

    todo_items: list[dict[str, object]] = []
    for tid in sorted(todo_ids):
        t = await v2_sync_repo.get_todo_item(
            session, user_id=user_id, item_id=tid, include_deleted=True
        )
        if t is None:
            continue
        todo_items.append(
            {
                "id": t.id,
                "list_id": t.list_id,
                "title": t.title,
                "tags": t.tags_json,
                "tzid": t.tzid,
                "client_updated_at_ms": t.client_updated_at_ms,
                "updated_at": t.updated_at,
                "deleted_at": t.deleted_at,
            }
        )

    return {
        "cursor": cursor,
        "next_cursor": next_cursor,
        "has_more": has_more,
        "changes": {
            "notes": notes,
            "todo_items": todo_items,
        },
    }
