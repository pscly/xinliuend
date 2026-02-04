from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Notification(BaseModel):
    id: str = Field(min_length=1, max_length=36)
    kind: str = Field(min_length=1, max_length=50)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    read_at: datetime | None = None


class NotificationListResponse(BaseModel):
    notifications: list[Notification] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


class UnreadCountResponse(BaseModel):
    unread_count: int
