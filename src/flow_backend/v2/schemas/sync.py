from __future__ import annotations

from pydantic import BaseModel

from .notes import Note
from .todo import TodoItem


class SyncMutation(BaseModel):
    resource: str
    entity_id: str
    op: str
    client_updated_at_ms: int
    data: dict[str, object] | None = None


class SyncApplied(BaseModel):
    resource: str
    entity_id: str


class SyncRejected(BaseModel):
    resource: str
    entity_id: str
    reason: str
    server: dict[str, object] | None = None


class SyncChanges(BaseModel):
    notes: list[Note]
    todo_items: list[TodoItem]


class SyncPullResponse(BaseModel):
    cursor: int
    next_cursor: int
    has_more: bool
    changes: SyncChanges


class SyncPushRequest(BaseModel):
    mutations: list[SyncMutation]


class SyncPushResponse(BaseModel):
    cursor: int
    applied: list[SyncApplied]
    rejected: list[SyncRejected]
