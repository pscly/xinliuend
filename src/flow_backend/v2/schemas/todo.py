from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TodoItem(BaseModel):
    id: str = Field(min_length=1, max_length=36)
    list_id: str = Field(min_length=1, max_length=36)
    title: str = Field(max_length=500)
    tags: list[str]
    tzid: str = Field(max_length=64)
    client_updated_at_ms: int
    updated_at: datetime
    deleted_at: datetime | None = None


class TodoItemCreateRequest(BaseModel):
    id: str | None = Field(default=None, min_length=1, max_length=36)
    list_id: str = Field(min_length=1, max_length=36)
    title: str = Field(min_length=1, max_length=500)
    tags: list[str] = Field(default_factory=list)
    tzid: str | None = Field(default=None, max_length=64)
    client_updated_at_ms: int | None = Field(default=None, ge=0)


class TodoItemPatchRequest(BaseModel):
    # All fields are optional, but at least one must be provided.
    list_id: str | None = Field(default=None, max_length=36)
    title: str | None = Field(default=None, min_length=1, max_length=500)
    tags: list[str] | None = None
    tzid: str | None = Field(default=None, max_length=64)
    client_updated_at_ms: int = Field(ge=0)


class TodoItemRestoreRequest(BaseModel):
    client_updated_at_ms: int = Field(ge=0)


class TodoItemList(BaseModel):
    items: list[TodoItem] = Field(default_factory=list)
    total: int
    limit: int
    offset: int
