from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Attachment(BaseModel):
    id: str = Field(min_length=1, max_length=36)
    note_id: str = Field(min_length=1, max_length=36)

    filename: str | None = Field(default=None, max_length=255)
    content_type: str | None = Field(default=None, max_length=255)
    size_bytes: int

    storage_key: str = Field(min_length=1, max_length=512)
    created_at: datetime
