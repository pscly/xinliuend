from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from flow_backend.memos_client import MemosClient, MemosClientError

_ORIGINAL_ASYNC_CLIENT = httpx.AsyncClient


@pytest.mark.anyio
async def test_memos_client_get_current_user_with_bearer_parses_auth_me(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["authorization"] == "Bearer pasted-token"
        return httpx.Response(
            200,
            json={"user": {"name": "users/42", "username": "alice"}},
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

    info = await client.get_current_user_with_bearer("pasted-token")

    assert info["username"] == "alice"
    assert info["user_id"] == 42
    assert requests[0].url.path == "/api/v1/auth/me"


@pytest.mark.anyio
async def test_memos_client_sign_in_and_create_pat_prefer_latest_endpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8") or "{}")
        calls.append((request.method, request.url.path, payload))
        if request.url.path == "/api/v1/auth/signin":
            assert payload["passwordCredentials"] == {"username": "alice", "password": "secret123x"}
            return httpx.Response(
                200,
                json={
                    "user": {"name": "users/42", "username": "alice"},
                    "accessToken": "signin-access-token",
                },
            )
        if request.url.path == "/api/v1/users/42/personalAccessTokens":
            assert request.headers["authorization"] == "Bearer signin-access-token"
            assert payload == {
                "parent": "users/42",
                "description": "flow token",
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

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    client = MemosClient(base_url="https://memos.test", admin_token="admin", timeout_seconds=3)

    signin = await client.sign_in_with_password(username="alice", app_password="secret123")
    token = await client.create_personal_access_token_with_bearer(
        user_id=signin["user_id"],
        bearer_token=signin["access_token"],
        description="flow token",
    )

    # `name` was added so callers can address users by `users/<username>` on new Memos.
    assert signin == {
        "access_token": "signin-access-token",
        "username": "alice",
        "user_id": 42,
        "name": "users/42",
    }
    assert token == "pat-token"
    assert [c[1] for c in calls] == [
        "/api/v1/auth/signin",
        "/api/v1/users/42/personalAccessTokens",
    ]


@pytest.mark.anyio
async def test_memos_client_create_pat_falls_back_to_legacy_access_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/api/v1/users/7/personalAccessTokens":
            return httpx.Response(404, json={"error": "not found"})
        if request.url.path == "/api/v1/users/7/accessTokens":
            return httpx.Response(200, json={"accessToken": "legacy-token"})
        return httpx.Response(500, json={"error": "unexpected"})

    class FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._client = _ORIGINAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler))

        async def __aenter__(self) -> httpx.AsyncClient:
            return self._client

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            await self._client.aclose()

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    client = MemosClient(base_url="https://memos.test", admin_token="admin", timeout_seconds=3)

    token = await client.create_personal_access_token_with_bearer(
        user_id=7,
        bearer_token="bearer",
        description="flow token",
    )

    assert token == "legacy-token"
    assert paths == ["/api/v1/users/7/personalAccessTokens", "/api/v1/users/7/accessTokens"]


@pytest.mark.anyio
async def test_memos_client_get_current_user_invalid_token_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(401, json={"message": "unauthorized"})

    class FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._client = _ORIGINAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler))

        async def __aenter__(self) -> httpx.AsyncClient:
            return self._client

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            await self._client.aclose()

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    client = MemosClient(base_url="https://memos.test", admin_token="admin", timeout_seconds=3)

    with pytest.raises(MemosClientError, match="Get current user failed"):
        await client.get_current_user_with_bearer("bad-token")
