from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field
from pydantic import model_validator


class Note(BaseModel):
    id: str = Field(min_length=1, max_length=36)
    title: str = Field(max_length=500)
    body_md: str = Field(max_length=20000)
    tags: list[str]
    client_updated_at_ms: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class NoteCreateRequest(BaseModel):
    id: str | None = Field(default=None, min_length=1, max_length=36)
    title: str | None = Field(default=None, max_length=500)
    body_md: str = Field(min_length=1, max_length=20000)
    tags: list[str] = Field(default_factory=list)
    client_updated_at_ms: int | None = Field(default=None, ge=0)


class NotePatchRequest(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    body_md: str | None = Field(default=None, max_length=20000)
    tags: list[str] | None = None
    client_updated_at_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _ensure_any_field_present(self) -> "NotePatchRequest":
        if self.title is None and self.body_md is None and self.tags is None:
            raise ValueError("at least one field must be provided")
        return self


class NoteRestoreRequest(BaseModel):
    client_updated_at_ms: int = Field(ge=0)


class NoteList(BaseModel):
    items: list[Note] = Field(default_factory=list)
    total: int
    limit: int
    offset: int
