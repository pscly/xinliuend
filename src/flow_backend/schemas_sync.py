from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from flow_backend.schemas_settings import SettingOut
from flow_backend.schemas_todo import TodoItemOut
from flow_backend.v2.schemas.collections import CollectionItem as CollectionItemOut
from flow_backend.v2.schemas.notes import Note as NoteOut


SyncResource = Literal[
    "note",
    "user_setting",
    "todo_list",
    "todo_item",
    "todo_occurrence",
    "collection_item",
]
SyncOp = Literal["upsert", "delete"]


class SyncMutation(BaseModel):
    resource: SyncResource
    op: SyncOp
    entity_id: str = Field(min_length=1, max_length=128)
    client_updated_at_ms: int = 0
    data: dict[str, Any] = Field(default_factory=dict)


class SyncPushRequest(BaseModel):
    mutations: list[SyncMutation] = Field(default_factory=list)


class SyncApplied(BaseModel):
    resource: str
    entity_id: str


class SyncRejected(BaseModel):
    resource: str
    entity_id: str
    reason: str
    server: dict[str, Any] | None = None


class SyncPushResponse(BaseModel):
    cursor: int
    applied: list[SyncApplied] = Field(default_factory=list)
    rejected: list[SyncRejected] = Field(default_factory=list)


class SyncTodoListOut(BaseModel):
    id: str = Field(min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=200)
    color: str | None = Field(default=None, max_length=32)
    sort_order: int
    archived: bool
    client_updated_at_ms: int
    updated_at: datetime
    deleted_at: datetime | None = None


class SyncTodoOccurrenceOut(BaseModel):
    id: str = Field(min_length=1, max_length=36)
    item_id: str = Field(min_length=1, max_length=36)
    tzid: str = Field(max_length=64)
    recurrence_id_local: str = Field(min_length=19, max_length=19)

    status_override: str | None = Field(default=None, max_length=20)
    title_override: str | None = Field(default=None, max_length=500)
    note_override: str | None = Field(default=None, max_length=10000)
    due_at_override_local: str | None = Field(default=None, max_length=19)
    completed_at_local: str | None = Field(default=None, max_length=19)

    client_updated_at_ms: int
    updated_at: datetime
    deleted_at: datetime | None = None


class SyncChanges(BaseModel):
    notes: list[NoteOut] = Field(default_factory=list)
    user_settings: list[SettingOut] = Field(default_factory=list)
    todo_lists: list[SyncTodoListOut] = Field(default_factory=list)
    todo_items: list[TodoItemOut] = Field(default_factory=list)
    todo_occurrences: list[SyncTodoOccurrenceOut] = Field(default_factory=list)
    collection_items: list[CollectionItemOut] = Field(default_factory=list)


class SyncPullResponse(BaseModel):
    cursor: int
    next_cursor: int
    has_more: bool
    changes: SyncChanges
