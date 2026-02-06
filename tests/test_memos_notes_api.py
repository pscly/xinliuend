from __future__ import annotations

import json

import httpx
import pytest

from flow_backend.integrations.memos_notes_api import (
    HttpxMemosNotesAPI,
    MemosNotesError,
    memo_id_from_remote_id,
    sha256_hex,
)
from flow_backend.integrations.memos_notes_api import _extract_list, _parse_memo


def test_sha256_hex_is_stable() -> None:
    assert sha256_hex("hello") == sha256_hex("hello")
    assert sha256_hex("hello") != sha256_hex("hello2")


def test_memo_id_from_remote_id() -> None:
    assert memo_id_from_remote_id("123") == "123"
    assert memo_id_from_remote_id("memos/123") == "123"
    assert memo_id_from_remote_id("https://x.example/api/memos/456") == "456"

    with pytest.raises(MemosNotesError):
        memo_id_from_remote_id("")


def test_extract_list_supports_multiple_shapes() -> None:
    assert _extract_list([{"id": 1}, "x", 2]) == [{"id": 1}]
    assert _extract_list({"memos": [{"id": 1}, "x"]}) == [{"id": 1}]
    assert _extract_list({"items": [{"id": 2}]}) == [{"id": 2}]
    assert _extract_list({"data": [{"id": 3}]}) == [{"id": 3}]
    assert _extract_list({"unknown": [{"id": 4}]}) == []


def test_parse_memo_remote_id_and_deleted_flags() -> None:
    m1 = _parse_memo(
        {
            "name": "memos/1",
            "content": "hello",
            "updatedAt": "2026-02-01T00:00:00Z",
        }
    )
    assert m1.remote_id == "memos/1"
    assert m1.content == "hello"
    assert m1.updated_at_ms is not None
    assert m1.deleted is False

    m2 = _parse_memo({"id": 2, "content": "x", "rowStatus": "ARCHIVED"})
    assert m2.remote_id == "2"
    assert m2.deleted is True


@pytest.mark.anyio
async def test_httpx_memos_api_list_memos_fallback_endpoints() -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, str(request.url)))
        if request.url.path.endswith("/bad"):
            return httpx.Response(500, json={"error": "boom"})
        return httpx.Response(
            200,
            json={
                "memos": [
                    {
                        "name": "memos/1",
                        "content": "hello",
                        "updateTime": "2026-02-01T00:00:00Z",
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        api = HttpxMemosNotesAPI(
            base_url="https://example.com",
            bearer_token="tok",
            timeout_seconds=3,
            list_endpoints=["/bad", "/ok"],
            upsert_endpoints=["/memos"],
            delete_endpoints=["/memos/{memo_id}"],
            client=client,
        )
        memos = await api.list_memos()
        assert len(memos) == 1
        assert memos[0].remote_id == "memos/1"

    assert len(calls) >= 2


@pytest.mark.anyio
async def test_httpx_memos_api_create_update_delete_happy_path_and_fallbacks() -> None:
    state = {
        "create_calls": 0,
        "delete_calls": 0,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        # create_memo: first payload fails, second payload succeeds
        if request.method == "POST":
            state["create_calls"] += 1
            if state["create_calls"] == 1:
                return httpx.Response(400, json={"error": "bad payload"})
            payload = json.loads(request.content.decode("utf-8") or "{}")
            content = payload.get("content") or (payload.get("memo") or {}).get("content") or ""
            return httpx.Response(200, json={"name": "memos/123", "content": content})

        # update_memo
        if request.method == "PATCH" and request.url.path.endswith("/321"):
            payload = json.loads(request.content.decode("utf-8") or "{}")
            content = payload.get("content") or (payload.get("memo") or {}).get("content") or ""
            return httpx.Response(200, json={"name": "memos/321", "content": content})

        # delete_memo: simulate 405 for DELETE then 200 for PATCH rowStatus
        if request.url.path.endswith("/999"):
            if request.method == "DELETE":
                state["delete_calls"] += 1
                return httpx.Response(405, json={"error": "method not allowed"})
            if request.method == "PATCH":
                return httpx.Response(200, json={"ok": True})

        return httpx.Response(404, json={"error": "not found"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        api = HttpxMemosNotesAPI(
            base_url="https://example.com",
            bearer_token="tok",
            timeout_seconds=3,
            list_endpoints=["/memos"],
            upsert_endpoints=["/memos"],
            delete_endpoints=["/memos/{memo_id}"],
            client=client,
        )

        created = await api.create_memo(content="hi")
        assert created.remote_id == "memos/123"
        assert created.content == "hi"

        updated = await api.update_memo(remote_id="memos/321", content="u")
        assert updated.remote_id == "memos/321"
        assert updated.content == "u"

        await api.delete_memo(remote_id="memos/999")

    assert state["create_calls"] >= 2
    assert state["delete_calls"] == 1
