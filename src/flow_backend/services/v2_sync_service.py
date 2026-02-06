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
    plan_mutation,
    validate_payload_for_resource,
)
from flow_backend.models import TodoItem, TodoItemOccurrence, TodoList, UserSetting, utc_now
from flow_backend.models_notes import Note
from flow_backend.repositories import note_revisions_repo, v2_sync_repo
from flow_backend.services.notes_tags_service import set_note_tags
from flow_backend.sync_utils import clamp_client_updated_at_ms, now_ms, record_sync_event


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


def _serialize_setting(row: UserSetting) -> dict[str, object]:
    return {
        "key": row.key,
        "value_json": row.value_json,
        "client_updated_at_ms": row.client_updated_at_ms,
        "updated_at": row.updated_at,
        "deleted_at": row.deleted_at,
    }


def _serialize_list(row: TodoList) -> dict[str, object]:
    return {
        "id": row.id,
        "name": row.name,
        "color": row.color,
        "sort_order": row.sort_order,
        "archived": row.archived,
        "client_updated_at_ms": row.client_updated_at_ms,
        "updated_at": row.updated_at,
        "deleted_at": row.deleted_at,
    }


def _serialize_item(row: TodoItem) -> dict[str, object]:
    return {
        "id": row.id,
        "list_id": row.list_id,
        "parent_id": row.parent_id,
        "title": row.title,
        "note": row.note,
        "status": row.status,
        "priority": row.priority,
        "due_at_local": row.due_at_local,
        "completed_at_local": row.completed_at_local,
        "sort_order": row.sort_order,
        "tags": row.tags_json,
        "is_recurring": row.is_recurring,
        "rrule": row.rrule,
        "dtstart_local": row.dtstart_local,
        "tzid": row.tzid,
        "reminders": row.reminders_json,
        "client_updated_at_ms": row.client_updated_at_ms,
        "updated_at": row.updated_at,
        "deleted_at": row.deleted_at,
    }


def _serialize_occurrence(row: TodoItemOccurrence) -> dict[str, object]:
    return {
        "id": row.id,
        "item_id": row.item_id,
        "tzid": row.tzid,
        "recurrence_id_local": row.recurrence_id_local,
        "status_override": row.status_override,
        "title_override": row.title_override,
        "note_override": row.note_override,
        "due_at_override_local": row.due_at_override_local,
        "completed_at_local": row.completed_at_local,
        "client_updated_at_ms": row.client_updated_at_ms,
        "updated_at": row.updated_at,
        "deleted_at": row.deleted_at,
    }


def _validate_recurring_fields(
    is_recurring: bool, rrule: str | None, dtstart_local: str | None
) -> str | None:
    if not is_recurring:
        return None
    if not (rrule and str(rrule).strip()):
        return "rrule is required"
    if not (dtstart_local and str(dtstart_local).strip()):
        return "dtstart_local is required"
    return None


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
        server=_serialize_item(item),
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
        resource_order: dict[str, int] = {
            "user_setting": 0,
            "todo_list": 1,
            "note": 1,
            "todo_item": 2,
            "todo_occurrence": 3,
        }
        for raw in sorted(
            mutations, key=lambda r: resource_order.get(str(r.get("resource") or ""), 99)
        ):
            resource = str(raw.get("resource") or "")
            entity_id = str(raw.get("entity_id") or "")
            op = str(raw.get("op") or "")
            incoming_ms_raw = _parse_int(raw.get("client_updated_at_ms"))
            incoming_ms = clamp_client_updated_at_ms(incoming_ms_raw) or now_ms()
            data = cast(dict[str, object] | None, raw.get("data"))

            if resource not in {
                "note",
                "user_setting",
                "todo_list",
                "todo_item",
                "todo_occurrence",
            }:
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

            if resource == "user_setting":
                server_setting = await v2_sync_repo.get_user_setting(
                    session, user_id=user_id, key=entity_id, include_deleted=True
                )
                if server_setting is not None and incoming_ms < int(
                    server_setting.client_updated_at_ms or 0
                ):
                    rejected.append(
                        {
                            "resource": resource,
                            "entity_id": entity_id,
                            "reason": "conflict",
                            "server": _serialize_setting(server_setting),
                        }
                    )
                    continue

                row = server_setting
                if row is None:
                    row = UserSetting(
                        user_id=user_id,
                        key=entity_id,
                        value_json={},
                        client_updated_at_ms=0,
                    )

                row.client_updated_at_ms = incoming_ms
                row.updated_at = utc_now()
                if op == "delete":
                    row.deleted_at = utc_now()
                else:
                    value_obj = dict((data or {}).get("value_json") or {})
                    row.value_json = value_obj
                    row.deleted_at = None

                session.add(row)
                record_sync_event(session, user_id, "user_setting", entity_id, op)
                applied.append({"resource": resource, "entity_id": entity_id})
                continue

            if resource == "todo_list":
                server_list = await v2_sync_repo.get_todo_list(
                    session, user_id=user_id, list_id=entity_id, include_deleted=True
                )
                if server_list is not None and incoming_ms < int(
                    server_list.client_updated_at_ms or 0
                ):
                    rejected.append(
                        {
                            "resource": resource,
                            "entity_id": entity_id,
                            "reason": "conflict",
                            "server": _serialize_list(server_list),
                        }
                    )
                    continue

                row2 = server_list
                if row2 is None:
                    row2 = TodoList(
                        id=entity_id,
                        user_id=user_id,
                        name="tmp",
                        client_updated_at_ms=0,
                    )

                row2.client_updated_at_ms = incoming_ms
                row2.updated_at = utc_now()
                if op == "delete":
                    row2.deleted_at = utc_now()
                else:
                    payload = dict(data or {})
                    if "name" in payload:
                        row2.name = str(payload.get("name") or row2.name)
                    if "color" in payload:
                        color_obj = payload.get("color")
                        row2.color = str(color_obj) if isinstance(color_obj, str) else None
                    if "sort_order" in payload:
                        row2.sort_order = _parse_int(payload.get("sort_order"))
                    if "archived" in payload:
                        archived_obj = payload.get("archived")
                        row2.archived = (
                            bool(archived_obj)
                            if isinstance(archived_obj, bool)
                            else bool(archived_obj)
                        )
                    row2.deleted_at = None

                session.add(row2)
                record_sync_event(session, user_id, "todo_list", entity_id, op)
                applied.append({"resource": resource, "entity_id": entity_id})
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
                    record_sync_event(session, user_id, "note", entity_id, "delete")
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
                    record_sync_event(session, user_id, "note", entity_id, "upsert")
                    applied.append({"resource": resource, "entity_id": entity_id})
                    continue

            if resource == "todo_item":
                server_item = await v2_sync_repo.get_todo_item(
                    session, user_id=user_id, item_id=entity_id, include_deleted=True
                )
                server_row2 = (
                    _todo_server_snapshot(server_item) if server_item is not None else None
                )

                incoming_payload2 = dict(data or {}) if op == "upsert" else None
                if op == "upsert" and server_row2 is None:
                    list_id_in = str((data or {}).get("list_id") or "").strip()
                    if not list_id_in:
                        rejected.append(
                            {
                                "resource": resource,
                                "entity_id": entity_id,
                                "reason": "missing list_id",
                            }
                        )
                        continue

                plan2 = plan_mutation(
                    resource="todo_item",
                    entity_id=entity_id,
                    op=cast(Any, op),
                    incoming_client_updated_at_ms=incoming_ms,
                    incoming_payload=incoming_payload2,
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
                    record_sync_event(session, user_id, "todo_item", entity_id, "delete")
                    applied.append({"resource": resource, "entity_id": entity_id})
                    continue

                if isinstance(plan2.apply, ApplyUpsert):
                    payload3 = cast(dict[str, object], plan2.apply.data)
                    item = server_item

                    # Validate list existence when creating or changing list_id.
                    list_id_payload: str | None = None
                    if item is None:
                        list_id_payload = str(payload3.get("list_id") or "").strip()
                        if not list_id_payload:
                            rejected.append(
                                {
                                    "resource": resource,
                                    "entity_id": entity_id,
                                    "reason": "missing list_id",
                                }
                            )
                            continue
                    elif "list_id" in payload3:
                        list_id_payload = str(payload3.get("list_id") or "").strip()
                        if not list_id_payload:
                            rejected.append(
                                {
                                    "resource": resource,
                                    "entity_id": entity_id,
                                    "reason": "missing list_id",
                                }
                            )
                            continue

                    if list_id_payload is not None:
                        list_row = await v2_sync_repo.get_todo_list(
                            session,
                            user_id=user_id,
                            list_id=list_id_payload,
                            include_deleted=False,
                        )
                        if list_row is None:
                            rejected.append(
                                {
                                    "resource": resource,
                                    "entity_id": entity_id,
                                    "reason": "todo list not found",
                                }
                            )
                            continue

                    # Compute next recurring fields for validation.
                    current_is_recurring = bool(item.is_recurring) if item is not None else False
                    current_rrule = item.rrule if item is not None else None
                    current_dtstart = item.dtstart_local if item is not None else None

                    is_recurring_next = (
                        bool(payload3.get("is_recurring") or False)
                        if "is_recurring" in payload3
                        else current_is_recurring
                    )
                    rrule_next = (
                        (str(payload3.get("rrule") or "").strip() or None)
                        if "rrule" in payload3
                        else current_rrule
                    )
                    dtstart_next_obj = (
                        payload3.get("dtstart_local")
                        if "dtstart_local" in payload3
                        else current_dtstart
                    )
                    dtstart_next = (
                        str(dtstart_next_obj) if isinstance(dtstart_next_obj, str) else None
                    )

                    recurring_reason = _validate_recurring_fields(
                        is_recurring_next, rrule_next, dtstart_next
                    )
                    if recurring_reason is not None:
                        rejected.append(
                            {
                                "resource": resource,
                                "entity_id": entity_id,
                                "reason": recurring_reason,
                            }
                        )
                        continue

                    if item is None:
                        title_in = str(payload3.get("title") or "tmp").strip() or "tmp"
                        tzid_in = str(payload3.get("tzid") or "").strip()
                        item = TodoItem(
                            id=entity_id,
                            user_id=user_id,
                            list_id=cast(str, list_id_payload),
                            title=title_in,
                            tzid=tzid_in or settings.default_tzid,
                            client_updated_at_ms=plan2.apply.client_updated_at_ms,
                            updated_at=utc_now(),
                        )

                    if list_id_payload is not None:
                        item.list_id = list_id_payload

                    if "parent_id" in payload3:
                        parent_obj = payload3.get("parent_id")
                        item.parent_id = (
                            str(parent_obj).strip()
                            if isinstance(parent_obj, str) and parent_obj.strip()
                            else None
                        )
                    if "title" in payload3:
                        title_obj = str(payload3.get("title") or "").strip()
                        if title_obj:
                            item.title = title_obj
                    if "note" in payload3:
                        item.note = str(payload3.get("note") or "")
                    if "status" in payload3:
                        item.status = str(payload3.get("status") or "open")
                    if "priority" in payload3:
                        item.priority = _parse_int(payload3.get("priority"))
                    if "due_at_local" in payload3:
                        due_obj = payload3.get("due_at_local")
                        item.due_at_local = str(due_obj) if isinstance(due_obj, str) else None
                    if "completed_at_local" in payload3:
                        done_obj = payload3.get("completed_at_local")
                        item.completed_at_local = (
                            str(done_obj) if isinstance(done_obj, str) else None
                        )
                    if "sort_order" in payload3:
                        item.sort_order = _parse_int(payload3.get("sort_order"))
                    if "tags" in payload3:
                        tags_obj = payload3.get("tags")
                        if isinstance(tags_obj, list):
                            tags_list = cast(list[object], tags_obj)
                            item.tags_json = [str(t) for t in tags_list if str(t).strip()]
                        else:
                            item.tags_json = []
                    if "tzid" in payload3:
                        tzid_in = str(payload3.get("tzid") or "").strip()
                        item.tzid = tzid_in or settings.default_tzid
                    if "reminders" in payload3:
                        rem_obj = payload3.get("reminders")
                        if isinstance(rem_obj, list):
                            rem_list = cast(list[object], rem_obj)
                            item.reminders_json = [
                                cast(dict[str, object], r) for r in rem_list if isinstance(r, dict)
                            ]
                        else:
                            item.reminders_json = []

                    item.is_recurring = is_recurring_next
                    item.rrule = rrule_next
                    item.dtstart_local = dtstart_next
                    item.client_updated_at_ms = plan2.apply.client_updated_at_ms
                    item.updated_at = utc_now()
                    item.deleted_at = None

                    session.add(item)
                    record_sync_event(session, user_id, "todo_item", entity_id, "upsert")
                    applied.append({"resource": resource, "entity_id": entity_id})
                    continue

            if resource == "todo_occurrence":
                server_occ = await v2_sync_repo.get_todo_occurrence(
                    session, user_id=user_id, occ_id=entity_id, include_deleted=True
                )
                if server_occ is not None and incoming_ms < int(
                    server_occ.client_updated_at_ms or 0
                ):
                    rejected.append(
                        {
                            "resource": resource,
                            "entity_id": entity_id,
                            "reason": "conflict",
                            "server": _serialize_occurrence(server_occ),
                        }
                    )
                    continue

                if op == "delete":
                    if server_occ is None:
                        applied.append({"resource": resource, "entity_id": entity_id})
                        continue
                    server_occ.deleted_at = utc_now()
                    server_occ.updated_at = utc_now()
                    server_occ.client_updated_at_ms = incoming_ms
                    session.add(server_occ)
                    record_sync_event(session, user_id, "todo_occurrence", entity_id, "delete")
                    applied.append({"resource": resource, "entity_id": entity_id})
                    continue

                payload4 = dict(data or {})

                occ = server_occ
                if occ is None:
                    item_id_in = str(payload4.get("item_id") or "").strip()
                    if not item_id_in:
                        rejected.append(
                            {
                                "resource": resource,
                                "entity_id": entity_id,
                                "reason": "missing item_id",
                            }
                        )
                        continue
                    rec_id_in = str(payload4.get("recurrence_id_local") or "").strip()
                    if not rec_id_in:
                        rejected.append(
                            {
                                "resource": resource,
                                "entity_id": entity_id,
                                "reason": "missing recurrence_id_local",
                            }
                        )
                        continue
                    item_row = await v2_sync_repo.get_todo_item(
                        session, user_id=user_id, item_id=item_id_in, include_deleted=False
                    )
                    if item_row is None:
                        rejected.append(
                            {
                                "resource": resource,
                                "entity_id": entity_id,
                                "reason": "todo item not found",
                            }
                        )
                        continue
                    tzid_in = str(payload4.get("tzid") or "").strip()
                    tzid = tzid_in or settings.default_tzid
                    occ = TodoItemOccurrence(
                        id=entity_id,
                        user_id=user_id,
                        item_id=item_id_in,
                        tzid=tzid,
                        recurrence_id_local=rec_id_in,
                        client_updated_at_ms=0,
                    )
                else:
                    if "item_id" in payload4:
                        item_id_in = str(payload4.get("item_id") or "").strip()
                        if not item_id_in:
                            rejected.append(
                                {
                                    "resource": resource,
                                    "entity_id": entity_id,
                                    "reason": "missing item_id",
                                }
                            )
                            continue
                        item_row = await v2_sync_repo.get_todo_item(
                            session, user_id=user_id, item_id=item_id_in, include_deleted=False
                        )
                        if item_row is None:
                            rejected.append(
                                {
                                    "resource": resource,
                                    "entity_id": entity_id,
                                    "reason": "todo item not found",
                                }
                            )
                            continue
                        occ.item_id = item_id_in
                    if "tzid" in payload4:
                        tzid_in = str(payload4.get("tzid") or "").strip()
                        occ.tzid = tzid_in or settings.default_tzid
                    if "recurrence_id_local" in payload4:
                        rec_id_in = str(payload4.get("recurrence_id_local") or "").strip()
                        if not rec_id_in:
                            rejected.append(
                                {
                                    "resource": resource,
                                    "entity_id": entity_id,
                                    "reason": "missing recurrence_id_local",
                                }
                            )
                            continue
                        occ.recurrence_id_local = rec_id_in

                if "status_override" in payload4:
                    occ.status_override = cast(str | None, payload4.get("status_override"))
                if "title_override" in payload4:
                    occ.title_override = cast(str | None, payload4.get("title_override"))
                if "note_override" in payload4:
                    occ.note_override = cast(str | None, payload4.get("note_override"))
                if "due_at_override_local" in payload4:
                    occ.due_at_override_local = cast(
                        str | None, payload4.get("due_at_override_local")
                    )
                if "completed_at_local" in payload4:
                    occ.completed_at_local = cast(str | None, payload4.get("completed_at_local"))

                occ.client_updated_at_ms = incoming_ms
                occ.updated_at = utc_now()
                occ.deleted_at = None
                session.add(occ)
                record_sync_event(session, user_id, "todo_occurrence", entity_id, "upsert")
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
    setting_keys: set[str] = set()
    list_ids: set[str] = set()
    todo_ids: set[str] = set()
    occ_ids: set[str] = set()
    for e in events:
        next_cursor = max(next_cursor, _parse_int(e.id))
        if e.resource == "note":
            note_ids.add(e.entity_id)
        elif e.resource == "user_setting":
            setting_keys.add(e.entity_id)
        elif e.resource == "todo_list":
            list_ids.add(e.entity_id)
        elif e.resource == "todo_item":
            todo_ids.add(e.entity_id)
        elif e.resource == "todo_occurrence":
            occ_ids.add(e.entity_id)

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

    user_settings: list[dict[str, object]] = []
    for key in sorted(setting_keys):
        s = await v2_sync_repo.get_user_setting(
            session, user_id=user_id, key=key, include_deleted=True
        )
        if s is None:
            continue
        user_settings.append(_serialize_setting(s))

    todo_lists: list[dict[str, object]] = []
    for lid in sorted(list_ids):
        todo_list = await v2_sync_repo.get_todo_list(
            session, user_id=user_id, list_id=lid, include_deleted=True
        )
        if todo_list is None:
            continue
        todo_lists.append(_serialize_list(todo_list))

    todo_items: list[dict[str, object]] = []
    for tid in sorted(todo_ids):
        t = await v2_sync_repo.get_todo_item(
            session, user_id=user_id, item_id=tid, include_deleted=True
        )
        if t is None:
            continue
        todo_items.append(_serialize_item(t))

    todo_occurrences: list[dict[str, object]] = []
    for oid in sorted(occ_ids):
        o = await v2_sync_repo.get_todo_occurrence(
            session, user_id=user_id, occ_id=oid, include_deleted=True
        )
        if o is None:
            continue
        todo_occurrences.append(_serialize_occurrence(o))

    return {
        "cursor": cursor,
        "next_cursor": next_cursor,
        "has_more": has_more,
        "changes": {
            "notes": notes,
            "user_settings": user_settings,
            "todo_lists": todo_lists,
            "todo_items": todo_items,
            "todo_occurrences": todo_occurrences,
        },
    }
