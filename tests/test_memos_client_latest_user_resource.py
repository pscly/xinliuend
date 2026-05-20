from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from flow_backend.memos_client import MemosClient

_ORIGINAL_ASYNC_CLIENT = httpx.AsyncClient


@pytest.mark.anyio
async def test_create_user_parses_latest_username_resource_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8") or "{}")
        calls.append((request.url.path, payload))
        assert request.url.path == "/api/v1/users"
        assert payload == {
            "user": {
                "username": "alice",
                "password": "secret123x",
                "role": "USER",
                "state": "NORMAL",
            },
            "userId": "alice",
        }
        return httpx.Response(
            200,
            json={
                "name": "users/alice",
                "role": "USER",
                "username": "alice",
                "state": "NORMAL",
            },
        )

    class FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._client = _ORIGINAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler))

        async def __aenter__(self) -> httpx.AsyncClient:
            return self._client

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            await self._client.aclose()

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    client = MemosClient(base_url="https://memos.test", admin_token="admin", timeout_seconds=3)

    resource = await client.create_user(
        endpoints=["/api/v1/users"], username="alice", password="secret123"
    )

    assert resource == "users/alice"
    assert len(calls) == 1


@pytest.mark.anyio
async def test_create_user_uses_numeric_id_when_latest_response_contains_integer_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8") or "{}")
        calls.append((request.url.path, payload))
        assert request.url.path == "/api/v1/users"
        return httpx.Response(
            200,
            json={
                "id": 42,
                "name": "users/42",
                "role": "USER",
                "username": "alice",
                "state": "NORMAL",
            },
        )

    class FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._client = _ORIGINAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler))

        async def __aenter__(self) -> httpx.AsyncClient:
            return self._client

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            await self._client.aclose()

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    client = MemosClient(base_url="https://memos.test", admin_token="admin", timeout_seconds=3)

    resource = await client.create_user(
        endpoints=["/api/v1/users"], username="alice", password="secret123"
    )

    assert resource == "users/42"
    assert len(calls) == 1


@pytest.mark.anyio
async def test_create_user_and_token_uses_existing_listed_resource_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, dict[str, Any], dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8") or "{}")
        calls.append((request.method, request.url.path, payload, dict(request.headers)))
        if request.method == "POST" and request.url.path == "/api/v1/users":
            return httpx.Response(
                409,
                json={"message": "already exists"},
            )
        if request.method == "PATCH" and request.url.path == "/api/v1/users/42":
            assert payload == {
                "name": "users/42",
                "password": "secret123x",
            }
            assert request.url.params.get("update_mask") == "password"
            return httpx.Response(200, json={"ok": True})
        if request.method == "POST" and request.url.path == "/api/v1/users/42/personalAccessTokens":
            assert payload == {
                "parent": "users/42",
                "description": "flow-alice-20260519000000",
                "expiresInDays": 0,
            }
            return httpx.Response(200, json={"token": "pat-token"})
        return httpx.Response(404, json={"error": "not found"})

    class FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._client = _ORIGINAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler))

        async def __aenter__(self) -> httpx.AsyncClient:
            return self._client

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            await self._client.aclose()

    class FrozenDatetime:
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001
            from datetime import datetime, timezone

            return datetime(2026, 5, 19, 0, 0, 0, tzinfo=timezone.utc if tz is None else tz)

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("flow_backend.memos_client.datetime", FrozenDatetime)
    client = MemosClient(base_url="https://memos.test", admin_token="admin", timeout_seconds=3)

    async def fake_find_user_name_by_username(self, username: str):  # noqa: ANN001
        assert username == "alice"
        return "users/42"

    monkeypatch.setattr(MemosClient, "find_user_name_by_username", fake_find_user_name_by_username)

    result = await client.create_user_and_token(
        create_user_endpoints=["/api/v1/users"],
        create_token_endpoints=["/api/v1/{user_name}/personalAccessTokens"],
        username="alice",
        password="secret123",
        allow_reset_existing_user_password=True,
    )

    assert result.memos_user_name == "users/42"
    assert result.memos_user_id == 42
    assert result.memos_token == "pat-token"


@pytest.mark.anyio
async def test_create_user_and_token_prefers_resource_name_for_latest_pat_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, dict[str, Any], dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8") or "{}")
        calls.append((request.method, request.url.path, payload, dict(request.headers)))
        if request.url.path == "/api/v1/users":
            return httpx.Response(
                200,
                json={
                    "name": "users/alice",
                    "role": "USER",
                    "username": "alice",
                    "state": "NORMAL",
                },
            )
        if request.url.path == "/api/v1/users/alice/personalAccessTokens":
            assert payload == {
                "parent": "users/alice",
                "description": "flow-alice-20260519000000",
                "expiresInDays": 0,
            }
            return httpx.Response(200, json={"token": "pat-token"})
        return httpx.Response(404, json={"error": "not found"})

    class FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._client = _ORIGINAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler))

        async def __aenter__(self) -> httpx.AsyncClient:
            return self._client

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            await self._client.aclose()

    class FrozenDatetime:
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001
            from datetime import datetime, timezone

            return datetime(2026, 5, 19, 0, 0, 0, tzinfo=timezone.utc if tz is None else tz)

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("flow_backend.memos_client.datetime", FrozenDatetime)
    client = MemosClient(base_url="https://memos.test", admin_token="admin", timeout_seconds=3)

    result = await client.create_user_and_token(
        create_user_endpoints=["/api/v1/users"],
        create_token_endpoints=["/api/v1/{user_name}/personalAccessTokens"],
        username="alice",
        password="secret123",
    )

    assert result.memos_user_name == "users/alice"
    assert result.memos_user_id is None
    assert result.memos_token == "pat-token"
    assert [f"{method} {path}" for method, path, _, _ in calls] == [
        "POST /api/v1/users",
        "POST /api/v1/users/alice/personalAccessTokens",
    ]
