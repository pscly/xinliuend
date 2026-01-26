from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column
from sqlalchemy.types import JSON as SAJSON
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True, min_length=1, max_length=64)
    password_hash: str = Field(min_length=1, max_length=255)

    memos_id: Optional[int] = Field(default=None, index=True)
    memos_token: str = Field(min_length=1)

    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class TenantRow(SQLModel):
    user_id: int = Field(index=True, foreign_key="users.id")

    client_updated_at_ms: int = Field(default=0, index=True)
    updated_at: datetime = Field(default_factory=utc_now, index=True)
    deleted_at: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class UserSetting(TenantRow, table=True):
    __tablename__ = "user_settings"

    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(min_length=1, max_length=128, index=True)
    value_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(SAJSON))


class TodoList(TenantRow, table=True):
    __tablename__ = "todo_lists"

    id: str = Field(primary_key=True, min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=200)
    color: Optional[str] = Field(default=None, max_length=32)
    sort_order: int = Field(default=0, index=True)
    archived: bool = Field(default=False, index=True)


class TodoItem(TenantRow, table=True):
    __tablename__ = "todo_items"

    id: str = Field(primary_key=True, min_length=1, max_length=36)
    list_id: str = Field(index=True, foreign_key="todo_lists.id", min_length=1, max_length=36)
    parent_id: Optional[str] = Field(default=None, index=True, foreign_key="todo_items.id", max_length=36)

    title: str = Field(min_length=1, max_length=500)
    note: str = Field(default="", max_length=10000)

    status: str = Field(default="open", index=True, max_length=20)
    priority: int = Field(default=0, index=True)
    due_at_local: Optional[str] = Field(default=None, max_length=19)  # YYYY-MM-DDTHH:mm:ss
    completed_at_local: Optional[str] = Field(default=None, max_length=19)

    sort_order: int = Field(default=0, index=True)
    tags_json: list[str] = Field(default_factory=list, sa_column=Column(SAJSON))

    # 复发任务（RRULE）字段：后端不展开，只存储并同步
    is_recurring: bool = Field(default=False, index=True)
    rrule: Optional[str] = Field(default=None, max_length=512)
    dtstart_local: Optional[str] = Field(default=None, max_length=19)
    tzid: str = Field(default="Asia/Shanghai", max_length=64)

    reminders_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(SAJSON))


class TodoItemOccurrence(TenantRow, table=True):
    __tablename__ = "todo_item_occurrences"

    id: str = Field(primary_key=True, min_length=1, max_length=36)
    item_id: str = Field(index=True, foreign_key="todo_items.id", min_length=1, max_length=36)
    tzid: str = Field(default="Asia/Shanghai", max_length=64)
    recurrence_id_local: str = Field(min_length=19, max_length=19, index=True)  # YYYY-MM-DDTHH:mm:ss

    status_override: Optional[str] = Field(default=None, max_length=20)
    title_override: Optional[str] = Field(default=None, max_length=500)
    note_override: Optional[str] = Field(default=None, max_length=10000)
    due_at_override_local: Optional[str] = Field(default=None, max_length=19)
    completed_at_local: Optional[str] = Field(default=None, max_length=19)


class SyncEvent(SQLModel, table=True):
    __tablename__ = "sync_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="users.id")

    resource: str = Field(index=True, max_length=50)
    entity_id: str = Field(index=True, max_length=128)
    action: str = Field(max_length=20)  # upsert / delete

    created_at: datetime = Field(default_factory=utc_now, index=True)
