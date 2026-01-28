from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SettingUpsertRequest(BaseModel):
    value_json: dict[str, Any] = Field(default_factory=dict)
    client_updated_at_ms: int = 0


class SettingDeleteRequest(BaseModel):
    client_updated_at_ms: int = 0
