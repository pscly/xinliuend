from __future__ import annotations

from pydantic import BaseModel, Field

from flow_backend.v2.schemas.notes import Note


class ShareCreateRequest(BaseModel):
    # Default expiry is applied server-side (7 days).
    # Max expiry is pinned at 30 days.
    expires_in_seconds: int | None = Field(default=None, ge=1, le=60 * 60 * 24 * 30)


class ShareCreated(BaseModel):
    share_id: str = Field(min_length=1, max_length=36)
    share_url: str
    share_token: str


class SharedAttachment(BaseModel):
    id: str = Field(min_length=1, max_length=36)
    filename: str | None = Field(default=None, max_length=255)
    content_type: str | None = Field(default=None, max_length=255)
    size_bytes: int


class SharedNote(BaseModel):
    note: Note
    attachments: list[SharedAttachment] = Field(default_factory=list)
