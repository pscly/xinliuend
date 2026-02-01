from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TodoItem(BaseModel):
    id: str = Field(min_length=1, max_length=36)
    title: str = Field(max_length=200)
    tags: list[str]
    tzid: str = Field(max_length=64)
    client_updated_at_ms: int
    updated_at: datetime
    deleted_at: datetime | None = None


class TodoItemList(BaseModel):
    items: list[TodoItem] = Field(default_factory=list)
    total: int
    limit: int
    offset: int
