from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


SyncResource = Literal["note", "user_setting", "todo_list", "todo_item", "todo_occurrence"]
SyncOp = Literal["upsert", "delete"]


class SyncMutation(BaseModel):
    resource: SyncResource
    op: SyncOp
    entity_id: str = Field(min_length=1, max_length=128)
    client_updated_at_ms: int = 0
    data: dict[str, Any] = Field(default_factory=dict)


class SyncPushRequest(BaseModel):
    mutations: list[SyncMutation] = Field(default_factory=list)


class SyncPullResponse(BaseModel):
    cursor: int
    next_cursor: int
    has_more: bool
    changes: dict[str, Any]
