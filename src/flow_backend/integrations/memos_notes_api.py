from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx


class MemosNotesError(RuntimeError):
    pass


@dataclass(frozen=True)
class MemosMemo:
    remote_id: str
    content: str
    updated_at_ms: int | None
    deleted: bool


class MemosNotesAPI(Protocol):
    async def list_memos(self) -> list[MemosMemo]: ...

    async def create_memo(self, *, content: str) -> MemosMemo: ...

    async def update_memo(self, *, remote_id: str, content: str) -> MemosMemo: ...

    async def delete_memo(self, *, remote_id: str) -> None: ...


def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


_REMOTE_ID_RE = re.compile(r"(\d+)$")


def memo_id_from_remote_id(remote_id: str) -> str:
    """Return the numeric memo id for endpoint templates.

    Accepts shapes like:
    - "memos/123" (newer v1 API)
    - "123"       (older / custom)
    """

    remote_id = (remote_id or "").strip()
    if not remote_id:
        raise MemosNotesError("empty remote_id")
    if remote_id.isdigit():
        return remote_id
    m = _REMOTE_ID_RE.search(remote_id)
    if m:
        return m.group(1)
    # Fall back to the last path segment.
    return remote_id.rsplit("/", 1)[-1]


def _parse_rfc3339_to_ms(value: str) -> int | None:
    try:
        # Allow trailing Z.
        v = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


def _parse_updated_at_ms(obj: dict[str, Any]) -> int | None:
    # Common shapes across Memos versions.
    for key in ("updatedTs", "updated_ts", "updateTs", "update_ts"):
        v = obj.get(key)
        if isinstance(v, int):
            return v * 1000
        if isinstance(v, float):
            return int(v * 1000)
        if isinstance(v, str) and v.isdigit():
            return int(v) * 1000

    for key in ("updateTime", "updatedAt", "updated_at"):
        v2 = obj.get(key)
        if isinstance(v2, str):
            ms = _parse_rfc3339_to_ms(v2)
            if ms is not None:
                return ms
    return None


def _parse_remote_id(obj: dict[str, Any]) -> str | None:
    name = obj.get("name")
    if isinstance(name, str) and name:
        return name
    memo_id = obj.get("id")
    if isinstance(memo_id, int):
        return str(memo_id)
    if isinstance(memo_id, str) and memo_id:
        return memo_id
    return None


def _parse_memo(obj: dict[str, Any]) -> MemosMemo:
    remote_id = _parse_remote_id(obj)
    if not remote_id:
        raise MemosNotesError(f"cannot parse memo remote id: {obj}")
    content = obj.get("content")
    if not isinstance(content, str):
        content = str(content or "")

    deleted = False
    for key in ("deleted", "archived"):
        v = obj.get(key)
        if isinstance(v, bool):
            deleted = deleted or v
    # Some versions use rowStatus="ARCHIVED".
    row_status = obj.get("rowStatus")
    if isinstance(row_status, str) and row_status.upper() in {"ARCHIVED", "DELETED"}:
        deleted = True

    return MemosMemo(
        remote_id=remote_id,
        content=content,
        updated_at_ms=_parse_updated_at_ms(obj),
        deleted=deleted,
    )


def _extract_list(data: object) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        if isinstance(data.get("memos"), list):
            return [x for x in data["memos"] if isinstance(x, dict)]
        if isinstance(data.get("items"), list):
            return [x for x in data["items"] if isinstance(x, dict)]
        if isinstance(data.get("data"), list):
            return [x for x in data["data"] if isinstance(x, dict)]
    return []


class HttpxMemosNotesAPI:
    def __init__(
        self,
        *,
        base_url: str,
        bearer_token: str,
        timeout_seconds: float,
        list_endpoints: list[str],
        upsert_endpoints: list[str],
        delete_endpoints: list[str],
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = bearer_token.strip()
        self._timeout = timeout_seconds
        self._list_eps = list_endpoints
        self._upsert_eps = upsert_endpoints
        self._delete_eps = delete_endpoints
        self._client = client

    def _headers(self) -> dict[str, str]:
        if not self._token:
            raise MemosNotesError("memos bearer token is empty")
        return {"Authorization": f"Bearer {self._token}"}

    async def _request(
        self, method: str, url: str, *, json: dict[str, Any] | None
    ) -> httpx.Response:
        if self._client is not None:
            return await self._client.request(method, url, headers=self._headers(), json=json)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await client.request(method, url, headers=self._headers(), json=json)

    async def list_memos(self) -> list[MemosMemo]:
        last_error = ""
        for ep in self._list_eps:
            url = f"{self._base_url}{ep}"
            resp = await self._request("GET", url, json=None)
            if 200 <= resp.status_code < 300:
                try:
                    items = _extract_list(resp.json())
                    return [_parse_memo(x) for x in items]
                except Exception as e:
                    raise MemosNotesError(f"list memos parse failed: {e}") from e
            last_error = f"{resp.status_code} {resp.text}"
        raise MemosNotesError(f"list memos failed. last_error={last_error}")

    async def create_memo(self, *, content: str) -> MemosMemo:
        last_error = ""
        payloads = [
            {"content": content},
            {"memo": {"content": content}},
            {"content": content, "visibility": "VISIBILITY_PRIVATE"},
        ]
        for ep in self._upsert_eps:
            url = f"{self._base_url}{ep}"
            for payload in payloads:
                resp = await self._request("POST", url, json=payload)
                if 200 <= resp.status_code < 300:
                    data = resp.json()
                    if isinstance(data, dict):
                        return _parse_memo(data)
                    raise MemosNotesError(f"create memo succeeded but bad response: {data}")
                last_error = f"{resp.status_code} {resp.text}"
        raise MemosNotesError(f"create memo failed. last_error={last_error}")

    async def update_memo(self, *, remote_id: str, content: str) -> MemosMemo:
        last_error = ""
        memo_id = memo_id_from_remote_id(remote_id)

        payloads = [
            {"content": content},
            {"memo": {"content": content}},
        ]

        # Try DELETE endpoint templates (often include {memo_id}).
        candidate_eps = []
        for ep in self._delete_eps:
            if "{memo_id}" in ep:
                candidate_eps.append(ep.replace("{memo_id}", memo_id))
        # Also try /memos/{id} derived from upsert endpoints.
        for ep in self._upsert_eps:
            candidate_eps.append(ep.rstrip("/") + f"/{memo_id}")

        for ep in candidate_eps:
            url = f"{self._base_url}{ep}"
            for payload in payloads:
                resp = await self._request("PATCH", url, json=payload)
                if 200 <= resp.status_code < 300:
                    data = resp.json()
                    if isinstance(data, dict):
                        return _parse_memo(data)
                    raise MemosNotesError(f"update memo succeeded but bad response: {data}")
                last_error = f"{resp.status_code} {resp.text}"
        raise MemosNotesError(f"update memo failed. last_error={last_error}")

    async def delete_memo(self, *, remote_id: str) -> None:
        last_error = ""
        memo_id = memo_id_from_remote_id(remote_id)
        for ep in self._delete_eps:
            ep2 = ep.replace("{memo_id}", memo_id)
            url = f"{self._base_url}{ep2}"
            resp = await self._request("DELETE", url, json=None)
            if 200 <= resp.status_code < 300:
                return
            # Some versions use POST/PATCH with rowStatus.
            if resp.status_code == 405:
                resp2 = await self._request("PATCH", url, json={"rowStatus": "ARCHIVED"})
                if 200 <= resp2.status_code < 300:
                    return
                last_error = f"{resp2.status_code} {resp2.text}"
                continue
            last_error = f"{resp.status_code} {resp.text}"
        raise MemosNotesError(f"delete memo failed. last_error={last_error}")
