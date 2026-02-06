from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class MemosMigrationSummary(BaseModel):
    remote_total: int = Field(default=0, ge=0)
    created_local: int = Field(default=0, ge=0)
    updated_local_from_remote: int = Field(default=0, ge=0)
    deleted_local_from_remote: int = Field(default=0, ge=0)
    conflicts: int = Field(default=0, ge=0)


class MemosMigrationResponse(BaseModel):
    ok: bool = True
    kind: Literal["preview", "apply"]
    summary: MemosMigrationSummary
    memos_base_url: str
    warnings: list[str] = Field(default_factory=list)
