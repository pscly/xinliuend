from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MemosMigrationSummary(BaseModel):
    remote_total: int = Field(default=0, ge=0)
    created_local: int = Field(default=0, ge=0)
    updated_local_from_remote: int = Field(default=0, ge=0)
    deleted_local_from_remote: int = Field(default=0, ge=0)
    conflicts: int = Field(default=0, ge=0)


class MemosMigrationResponse(BaseModel):
    ok: bool = True
    kind: Literal["preview", "apply"]
    summary: MemosMigrationSummary
    memos_base_url: str
    warnings: list[str] = Field(default_factory=list)


class MemosNoteItem(BaseModel):
    remote_id: str = Field(min_length=1, max_length=200)
    title: str = Field(default="", max_length=500)
    body_md: str = Field(default="", max_length=20000)
    updated_at: datetime | None = None
    deleted: bool = False
    source: Literal["memos"] = "memos"
    linked_local_note_id: str | None = Field(default=None, min_length=1, max_length=36)


class MemosNoteListResponse(BaseModel):
    items: list[MemosNoteItem] = Field(default_factory=list)
    total: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)
