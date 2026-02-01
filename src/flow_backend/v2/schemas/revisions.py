from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class NoteSnapshot(BaseModel):
    title: str = Field(default="", max_length=500)
    body_md: str = Field(default="", max_length=20000)
    tags: list[str] = Field(default_factory=list)
    client_updated_at_ms: int


class NoteRevision(BaseModel):
    id: str = Field(min_length=1, max_length=36)
    note_id: str = Field(min_length=1, max_length=36)
    kind: str = Field(max_length=20)
    snapshot: NoteSnapshot
    created_at: datetime
    reason: str | None = Field(default=None, max_length=500)


class NoteRevisionList(BaseModel):
    items: list[NoteRevision] = Field(default_factory=list)


class NoteRevisionRestoreRequest(BaseModel):
    client_updated_at_ms: int = Field(ge=0)
