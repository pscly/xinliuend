from __future__ import annotations

from typing import Any

import httpx
import pytest

from flow_backend.memos_client import MemosClient

_ORIGINAL_ASYNC_CLIENT = httpx.AsyncClient


def _make_fake_client_factory(handler):
    """Build a httpx.AsyncClient drop-in that routes through the MockTransport."""

    class FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._client = _ORIGINAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler))

        async def __aenter__(self) -> httpx.AsyncClient:
            return self._client

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            await self._client.aclose()

    return FakeAsyncClient


@pytest.mark.anyio
async def test_auth_me_parses_username_only_resource_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """New Memos releases return `users/<username>` instead of `users/<numeric_id>`.

    Older clients raised "Cannot parse Memos user identity" against that shape
    which surfaced to the operator as HTTP 502. The parser must accept the new
    shape, returning user_id=0 as a sentinel for "no numeric id".
    """

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/auth/me"
        assert request.headers["authorization"] == "Bearer pat-new"
        return httpx.Response(
            200,
            json={
                "user": {
                    "name": "users/pscly",
                    "username": "pscly",
                    "role": "ADMIN",
                    "email": "pscly@example.com",
                }
            },
        )

    monkeypatch.setattr(httpx, "AsyncClient", _make_fake_client_factory(handler))
    client = MemosClient(base_url="https://memos.test", admin_token="x", timeout_seconds=3)

    info = await client.get_current_user_with_bearer("pat-new")

    assert info["username"] == "pscly"
    assert info["user_id"] == 0  # sentinel: no numeric id in new Memos
    assert info["name"] == "users/pscly"


@pytest.mark.anyio
async def test_auth_me_legacy_numeric_id_still_parses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Older Memos releases return `users/<numeric_id>` — must keep working."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"user": {"name": "users/42", "username": "alice"}},
        )

    monkeypatch.setattr(httpx, "AsyncClient", _make_fake_client_factory(handler))
    client = MemosClient(base_url="https://memos.test", admin_token="x", timeout_seconds=3)

    info = await client.get_current_user_with_bearer("token")

    assert info["username"] == "alice"
    assert info["user_id"] == 42


@pytest.mark.anyio
async def test_update_user_password_prefers_username_url_when_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """New Memos addresses users by `users/<username>` for PATCH; old ones use numeric.

    When the caller knows the username, we should hit the username URL first.
    Older Memos returning 404 on that URL should still allow the numeric fallback.
    """

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/api/v1/users/pscly":
            assert request.method == "PATCH"
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(404, json={"message": "not found"})

    monkeypatch.setattr(httpx, "AsyncClient", _make_fake_client_factory(handler))
    client = MemosClient(base_url="https://memos.test", admin_token="x", timeout_seconds=3)

    # Pass both — username form should win on first try.
    await client.update_user_password(user_id=42, new_password="abc123", username="pscly")

    assert calls == ["/api/v1/users/pscly"]


@pytest.mark.anyio
async def test_update_user_password_falls_back_to_numeric_when_username_404s(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Older Memos doesn't have the username route — fall through to numeric id."""

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/api/v1/users/alice":
            return httpx.Response(404, json={"message": "not found"})
        if request.url.path == "/api/v1/users/7":
            assert request.method == "PATCH"
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(500, json={"message": "unexpected"})

    monkeypatch.setattr(httpx, "AsyncClient", _make_fake_client_factory(handler))
    client = MemosClient(base_url="https://memos.test", admin_token="x", timeout_seconds=3)

    await client.update_user_password(user_id=7, new_password="abc123", username="alice")

    assert calls == ["/api/v1/users/alice", "/api/v1/users/7"]


@pytest.mark.anyio
async def test_update_user_password_errors_clearly_when_no_id_or_username() -> None:
    from flow_backend.memos_client import MemosClientError

    client = MemosClient(base_url="https://memos.test", admin_token="x", timeout_seconds=3)
    with pytest.raises(MemosClientError, match="neither memos user id nor username is set"):
        await client.update_user_password(user_id=0, new_password="abc123", username=None)
