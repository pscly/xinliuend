from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from pydantic import model_validator


CollectionItemType = Literal["folder", "note_ref"]
CollectionRefType = Literal["flow_note", "memos_memo"]


class CollectionItem(BaseModel):
    id: str = Field(min_length=1, max_length=36)
    item_type: CollectionItemType
    parent_id: str | None = Field(default=None, max_length=36)
    name: str = Field(default="", max_length=500)
    color: str | None = Field(default=None, max_length=64)
    ref_type: CollectionRefType | None = None
    ref_id: str | None = Field(default=None, max_length=128)
    sort_order: int
    client_updated_at_ms: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None

    @model_validator(mode="after")
    def _validate_semantics(self) -> "CollectionItem":
        if self.item_type == "folder":
            if self.name.strip() == "":
                raise ValueError("name is required for folder")
            if self.ref_type is not None or self.ref_id is not None:
                raise ValueError("ref_type/ref_id must be None for folder")
            return self

        if self.ref_type is None or self.ref_id is None or self.ref_id.strip() == "":
            raise ValueError("ref_type and ref_id are required for note_ref")
        return self


class CollectionItemCreateRequest(BaseModel):
    id: str | None = Field(default=None, min_length=1, max_length=36)
    item_type: CollectionItemType
    parent_id: str | None = Field(default=None, max_length=36)
    name: str | None = Field(default=None, max_length=500)
    color: str | None = Field(default=None, max_length=64)
    ref_type: CollectionRefType | None = None
    ref_id: str | None = Field(default=None, max_length=128)
    sort_order: int | None = None
    client_updated_at_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_semantics(self) -> "CollectionItemCreateRequest":
        if self.item_type == "folder":
            if self.name is None or self.name.strip() == "":
                raise ValueError("name is required for folder")
            if self.ref_type is not None or self.ref_id is not None:
                raise ValueError("ref_type/ref_id must be None for folder")
            return self

        if self.ref_type is None or self.ref_id is None or self.ref_id.strip() == "":
            raise ValueError("ref_type and ref_id are required for note_ref")
        return self


class CollectionItemPatchRequest(BaseModel):
    parent_id: str | None = Field(default=None, max_length=36)
    name: str | None = Field(default=None, max_length=500)
    color: str | None = Field(default=None, max_length=64)
    ref_type: CollectionRefType | None = None
    ref_id: str | None = Field(default=None, max_length=128)
    sort_order: int | None = None
    client_updated_at_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _ensure_any_field_present(self) -> "CollectionItemPatchRequest":
        changed_fields = set(self.model_fields_set) - {"client_updated_at_ms"}
        if not changed_fields:
            raise ValueError("at least one field must be provided")

        if ("ref_type" in changed_fields) ^ ("ref_id" in changed_fields):
            raise ValueError("ref_type and ref_id must be provided together")

        if "ref_type" in changed_fields and "ref_id" in changed_fields:
            if self.ref_type is None and self.ref_id is not None:
                raise ValueError("ref_id must be None when ref_type is None")
            if self.ref_type is not None and (self.ref_id is None or self.ref_id.strip() == ""):
                raise ValueError("ref_id is required when ref_type is provided")

        return self


class CollectionItemMoveItem(BaseModel):
    id: str = Field(min_length=1, max_length=36)
    parent_id: str | None = Field(max_length=36)
    sort_order: int
    client_updated_at_ms: int = Field(ge=0)


class CollectionItemBatchDeleteItem(BaseModel):
    id: str = Field(min_length=1, max_length=36)
    client_updated_at_ms: int = Field(ge=0)


class CollectionItemList(BaseModel):
    items: list[CollectionItem] = Field(default_factory=list)
    total: int
    limit: int
    offset: int
