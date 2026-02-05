from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    ok: bool = True


class OkResponse(BaseModel):
    ok: bool = True


class IdResponse(BaseModel):
    id: str = Field(min_length=1)


class IdsResponse(BaseModel):
    ids: list[str] = Field(default_factory=list)

