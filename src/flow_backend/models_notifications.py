from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column
from sqlalchemy.types import JSON as SAJSON
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Notification(SQLModel, table=True):
    __tablename__ = "notifications"  # pyright: ignore[reportAssignmentType]

    id: str = Field(primary_key=True, min_length=1, max_length=36)
    # Recipient user.
    user_id: int = Field(index=True, foreign_key="users.id")

    # e.g. mention
    kind: str = Field(index=True, min_length=1, max_length=50)

    # Opaque per-kind payload. For mentions we store: share_token, note_id, comment_id, snippet.
    payload_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(SAJSON, nullable=False),
    )

    read_at: Optional[datetime] = Field(default=None, index=True)

    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now, index=True)
