from __future__ import annotations

import pytest

from flow_backend.domain.sync_planner import (
    PlanResult,
    ServerRowSnapshot,
    normalize_note_payload,
    plan_mutation,
    validate_payload_for_resource,
)


@pytest.mark.parametrize(
    "case",
    [
        {
            "name": "create applies",
            "server": None,
            "op": "upsert",
            "incoming_ms": 10,
            "payload": {"body_md": "hi", "title": "t", "tags": ["a"]},
            "expect_apply": True,
            "expect_reject": False,
        },
        {
            "name": "create missing body rejects",
            "server": None,
            "op": "upsert",
            "incoming_ms": 10,
            "payload": {"title": "t"},
            "expect_apply": False,
            "expect_reject": True,
        },
        {
            "name": "stale update rejects conflict",
            "server": ServerRowSnapshot(
                entity_id="n1",
                client_updated_at_ms=100,
                deleted=False,
                server={"client_updated_at_ms": 100},
            ),
            "op": "upsert",
            "incoming_ms": 10,
            "payload": {"body_md": "hi"},
            "expect_apply": False,
            "expect_reject": True,
        },
        {
            "name": "delete stale rejects conflict",
            "server": ServerRowSnapshot(
                entity_id="n1",
                client_updated_at_ms=100,
                deleted=False,
                server={"client_updated_at_ms": 100},
            ),
            "op": "delete",
            "incoming_ms": 10,
            "payload": None,
            "expect_apply": False,
            "expect_reject": True,
        },
        {
            "name": "delete non-existent applies idempotently",
            "server": None,
            "op": "delete",
            "incoming_ms": 10,
            "payload": None,
            "expect_apply": True,
            "expect_reject": False,
        },
        {
            "name": "upsert tombstoned rejects conflict",
            "server": ServerRowSnapshot(
                entity_id="n1",
                client_updated_at_ms=100,
                deleted=True,
                server={"client_updated_at_ms": 100, "deleted": True},
            ),
            "op": "upsert",
            "incoming_ms": 200,
            "payload": {"body_md": "hi"},
            "expect_apply": False,
            "expect_reject": True,
        },
    ],
    ids=lambda c: c["name"],
)
def test_notes_sync_planner_conflict_matrix(case):
    server = case["server"]
    payload = case["payload"]
    normalized = normalize_note_payload(payload or {}) if payload is not None else {}
    reason = validate_payload_for_resource("note", normalized, server_row=server)

    plan: PlanResult
    if reason is not None and case["op"] == "upsert":
        plan = PlanResult(apply=None, reject=None)
        # Simulate router/service-level validation rejection.
        assert reason
        assert case["expect_reject"]
        return

    plan = plan_mutation(
        resource="note",
        entity_id="n1",
        op=case["op"],
        incoming_client_updated_at_ms=case["incoming_ms"],
        incoming_payload=normalized or None,
        server_row=server,
    )

    assert (plan.apply is not None) == case["expect_apply"]
    assert (plan.reject is not None) == case["expect_reject"]
