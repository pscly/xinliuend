from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SettingUpsertRequest(BaseModel):
    value_json: dict[str, Any] = Field(default_factory=dict)
    client_updated_at_ms: int = 0


class SettingDeleteRequest(BaseModel):
    client_updated_at_ms: int = 0


class SettingItem(BaseModel):
    key: str = Field(min_length=1, max_length=128)
    value_json: dict[str, Any] = Field(default_factory=dict)
    client_updated_at_ms: int
    updated_at: datetime


class SettingsListResponse(BaseModel):
    items: list[SettingItem] = Field(default_factory=list)


class SettingOut(BaseModel):
    key: str = Field(min_length=1, max_length=128)
    value_json: dict[str, Any] = Field(default_factory=dict)
    client_updated_at_ms: int
    updated_at: datetime
    deleted_at: datetime | None = None
