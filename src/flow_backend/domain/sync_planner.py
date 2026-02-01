from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast


Resource = Literal["note", "todo_item"]
Op = Literal["upsert", "delete"]


@dataclass(frozen=True)
class ServerRowSnapshot:
    entity_id: str
    client_updated_at_ms: int
    deleted: bool
    # Minimal server snapshot for client reconciliation.
    server: dict[str, object]


@dataclass(frozen=True)
class ApplyUpsert:
    entity_id: str
    client_updated_at_ms: int
    data: dict[str, object]


@dataclass(frozen=True)
class ApplyDelete:
    entity_id: str
    client_updated_at_ms: int


@dataclass(frozen=True)
class Reject:
    entity_id: str
    reason: str
    server: dict[str, object] | None = None


@dataclass(frozen=True)
class PlanResult:
    apply: ApplyUpsert | ApplyDelete | None
    reject: Reject | None


def _reject_conflict(server: ServerRowSnapshot) -> PlanResult:
    return PlanResult(
        apply=None,
        reject=Reject(entity_id=server.entity_id, reason="conflict", server=server.server),
    )


def plan_mutation(
    *,
    resource: Resource,
    entity_id: str,
    op: Op,
    incoming_client_updated_at_ms: int,
    incoming_payload: dict[str, object] | None,
    server_row: ServerRowSnapshot | None,
) -> PlanResult:
    """Pure conflict planner.

    - No DB/network/time.
    - Deterministic.
    """

    incoming_ms = int(incoming_client_updated_at_ms or 0)
    if incoming_ms <= 0:
        return PlanResult(
            apply=None,
            reject=Reject(entity_id=entity_id, reason="invalid client_updated_at_ms"),
        )

    if op not in {"upsert", "delete"}:
        return PlanResult(apply=None, reject=Reject(entity_id=entity_id, reason="invalid op"))

    if resource not in {"note", "todo_item"}:
        return PlanResult(apply=None, reject=Reject(entity_id=entity_id, reason="invalid resource"))

    # Missing server row.
    if server_row is None:
        if op == "delete":
            # Idempotent delete.
            return PlanResult(
                apply=ApplyDelete(entity_id=entity_id, client_updated_at_ms=incoming_ms),
                reject=None,
            )

        data = dict(incoming_payload or {})
        return PlanResult(
            apply=ApplyUpsert(entity_id=entity_id, client_updated_at_ms=incoming_ms, data=data),
            reject=None,
        )

    # Stale update/delete.
    if incoming_ms < int(server_row.client_updated_at_ms or 0):
        return _reject_conflict(server_row)

    if op == "delete":
        return PlanResult(
            apply=ApplyDelete(entity_id=entity_id, client_updated_at_ms=incoming_ms), reject=None
        )

    # Upsert against an existing row.
    if server_row.deleted:
        # Tombstoned rows can only be restored via explicit restore endpoints.
        return _reject_conflict(server_row)

    data = dict(incoming_payload or {})
    return PlanResult(
        apply=ApplyUpsert(entity_id=entity_id, client_updated_at_ms=incoming_ms, data=data),
        reject=None,
    )


def normalize_note_payload(payload: dict[str, object]) -> dict[str, object]:
    title = str(payload.get("title") or "")
    body_md_obj = payload.get("body_md")
    body_md = str(body_md_obj) if body_md_obj is not None else ""
    tags_obj = payload.get("tags")

    out: dict[str, object] = {}
    if title:
        out["title"] = title
    if body_md_obj is not None:
        out["body_md"] = body_md
    if isinstance(tags_obj, list):
        tags_list = cast(list[object], tags_obj)
        out["tags"] = [str(t) for t in tags_list if str(t).strip()]
    return out


def normalize_todo_item_payload(payload: dict[str, object]) -> dict[str, object]:
    out: dict[str, object] = {}
    list_id = str(payload.get("list_id") or "").strip()
    if list_id:
        out["list_id"] = list_id

    title = str(payload.get("title") or "").strip()
    if title:
        out["title"] = title

    tags_obj = payload.get("tags")
    if isinstance(tags_obj, list):
        tags_list = cast(list[object], tags_obj)
        out["tags"] = [str(t) for t in tags_list if str(t).strip()]

    tzid = str(payload.get("tzid") or "").strip()
    if tzid:
        out["tzid"] = tzid
    return out


def validate_payload_for_resource(
    resource: Resource, normalized: dict[str, object], *, server_row: ServerRowSnapshot | None
) -> str | None:
    """Return rejection reason if invalid, else None."""
    if resource == "note":
        # Create requires body_md.
        if server_row is None and "body_md" not in normalized:
            return "missing body_md"
        return None

    if resource == "todo_item":
        # Create requires list_id.
        if server_row is None and not str(normalized.get("list_id") or "").strip():
            return "missing list_id"
        return None
