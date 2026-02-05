from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from flow_backend.validators import validate_local_dt


class TodoListUpsertRequest(BaseModel):
    id: Optional[str] = None
    name: str = Field(min_length=1, max_length=200)
    color: Optional[str] = Field(default=None, max_length=32)
    sort_order: int = 0
    archived: bool = False
    client_updated_at_ms: int = 0


class TodoListPatchRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    color: Optional[str] = Field(default=None, max_length=32)
    sort_order: Optional[int] = None
    archived: Optional[bool] = None
    client_updated_at_ms: int = 0


class TodoListReorderItem(BaseModel):
    id: str = Field(min_length=1, max_length=36)
    sort_order: int
    client_updated_at_ms: int = 0


class TodoItemUpsertRequest(BaseModel):
    id: Optional[str] = None
    list_id: str = Field(min_length=1, max_length=36)
    parent_id: Optional[str] = Field(default=None, max_length=36)

    title: str = Field(min_length=1, max_length=500)
    note: str = Field(default="", max_length=10000)

    status: str = Field(default="open", max_length=20)
    priority: int = 0
    due_at_local: Optional[str] = Field(default=None, max_length=19)
    completed_at_local: Optional[str] = Field(default=None, max_length=19)

    sort_order: int = 0
    tags: list[str] = Field(default_factory=list)

    is_recurring: bool = False
    rrule: Optional[str] = Field(default=None, max_length=512)
    dtstart_local: Optional[str] = Field(default=None, max_length=19)
    tzid: Optional[str] = Field(default=None, max_length=64)
    reminders: list[dict[str, Any]] = Field(default_factory=list)

    client_updated_at_ms: int = 0

    @field_validator("due_at_local")
    @classmethod
    def _validate_due_at_local(cls, v: str | None) -> str | None:
        return validate_local_dt(v, "due_at_local")

    @field_validator("completed_at_local")
    @classmethod
    def _validate_completed_at_local(cls, v: str | None) -> str | None:
        return validate_local_dt(v, "completed_at_local")

    @field_validator("dtstart_local")
    @classmethod
    def _validate_dtstart_local(cls, v: str | None) -> str | None:
        return validate_local_dt(v, "dtstart_local")

    @field_validator("rrule")
    @classmethod
    def _validate_rrule(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not v.strip():
            raise ValueError("rrule 不能为空字符串")
        return v.strip()

    @field_validator("is_recurring")
    @classmethod
    def _validate_recurring_requires_fields(cls, v: bool, info):  # type: ignore[no-untyped-def]
        # Pydantic v2：跨字段校验更适合 model_validator，但这里保持轻量，逻辑在路由层兜底
        return v


class TodoItemPatchRequest(BaseModel):
    list_id: Optional[str] = Field(default=None, max_length=36)
    parent_id: Optional[str] = Field(default=None, max_length=36)

    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    note: Optional[str] = Field(default=None, max_length=10000)

    status: Optional[str] = Field(default=None, max_length=20)
    priority: Optional[int] = None
    due_at_local: Optional[str] = Field(default=None, max_length=19)
    completed_at_local: Optional[str] = Field(default=None, max_length=19)

    sort_order: Optional[int] = None
    tags: Optional[list[str]] = None

    is_recurring: Optional[bool] = None
    rrule: Optional[str] = Field(default=None, max_length=512)
    dtstart_local: Optional[str] = Field(default=None, max_length=19)
    tzid: Optional[str] = Field(default=None, max_length=64)
    reminders: Optional[list[dict[str, Any]]] = None

    client_updated_at_ms: int = 0

    @field_validator("due_at_local")
    @classmethod
    def _validate_due_at_local(cls, v: str | None) -> str | None:
        return validate_local_dt(v, "due_at_local")

    @field_validator("completed_at_local")
    @classmethod
    def _validate_completed_at_local(cls, v: str | None) -> str | None:
        return validate_local_dt(v, "completed_at_local")

    @field_validator("dtstart_local")
    @classmethod
    def _validate_dtstart_local(cls, v: str | None) -> str | None:
        return validate_local_dt(v, "dtstart_local")


class TodoItemRestoreRequest(BaseModel):
    client_updated_at_ms: int = 0


class TodoItemOccurrenceUpsertRequest(BaseModel):
    id: Optional[str] = None
    item_id: str = Field(min_length=1, max_length=36)
    tzid: Optional[str] = Field(default=None, max_length=64)
    recurrence_id_local: str = Field(min_length=19, max_length=19)

    status_override: Optional[str] = Field(default=None, max_length=20)
    title_override: Optional[str] = Field(default=None, max_length=500)
    note_override: Optional[str] = Field(default=None, max_length=10000)
    due_at_override_local: Optional[str] = Field(default=None, max_length=19)
    completed_at_local: Optional[str] = Field(default=None, max_length=19)

    client_updated_at_ms: int = 0

    @field_validator("recurrence_id_local")
    @classmethod
    def _validate_recurrence_id_local(cls, v: str) -> str:
        validate_local_dt(v, "recurrence_id_local")
        return v

    @field_validator("due_at_override_local")
    @classmethod
    def _validate_due_at_override_local(cls, v: str | None) -> str | None:
        return validate_local_dt(v, "due_at_override_local")

    @field_validator("completed_at_local")
    @classmethod
    def _validate_completed_at_local(cls, v: str | None) -> str | None:
        return validate_local_dt(v, "completed_at_local")


class TodoListItem(BaseModel):
    id: str = Field(min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=200)
    color: str | None = Field(default=None, max_length=32)
    sort_order: int
    archived: bool
    client_updated_at_ms: int
    updated_at: datetime


class TodoListListResponse(BaseModel):
    items: list[TodoListItem] = Field(default_factory=list)


class TodoItemOut(BaseModel):
    id: str = Field(min_length=1, max_length=36)
    list_id: str = Field(min_length=1, max_length=36)
    parent_id: str | None = Field(default=None, max_length=36)

    title: str = Field(max_length=500)
    note: str = Field(max_length=10000)

    status: str = Field(max_length=20)
    priority: int
    due_at_local: str | None = Field(default=None, max_length=19)
    completed_at_local: str | None = Field(default=None, max_length=19)

    sort_order: int
    tags: list[str] = Field(default_factory=list)

    is_recurring: bool
    rrule: str | None = Field(default=None, max_length=512)
    dtstart_local: str | None = Field(default=None, max_length=19)
    tzid: str = Field(max_length=64)
    reminders: list[dict[str, Any]] = Field(default_factory=list)

    client_updated_at_ms: int
    updated_at: datetime
    deleted_at: datetime | None = None


class TodoItemListResponse(BaseModel):
    items: list[TodoItemOut] = Field(default_factory=list)


class TodoOccurrenceOut(BaseModel):
    id: str = Field(min_length=1, max_length=36)
    item_id: str = Field(min_length=1, max_length=36)
    tzid: str = Field(max_length=64)
    recurrence_id_local: str = Field(min_length=19, max_length=19)

    status_override: str | None = Field(default=None, max_length=20)
    title_override: str | None = Field(default=None, max_length=500)
    note_override: str | None = Field(default=None, max_length=10000)
    due_at_override_local: str | None = Field(default=None, max_length=19)
    completed_at_local: str | None = Field(default=None, max_length=19)

    client_updated_at_ms: int
    updated_at: datetime


class TodoOccurrenceListResponse(BaseModel):
    items: list[TodoOccurrenceOut] = Field(default_factory=list)
