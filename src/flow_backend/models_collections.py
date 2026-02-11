from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TenantRowBase(SQLModel):
    # Keep this module standalone to avoid import cycles. Mirrors flow_backend.models.TenantRow.
    user_id: int = Field(index=True, foreign_key="users.id")

    client_updated_at_ms: int = Field(default=0, index=True)
    updated_at: datetime = Field(default_factory=utc_now, index=True)
    deleted_at: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class CollectionItem(TenantRowBase, table=True):
    __tablename__ = "collection_items"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (Index("ix_collection_items_ref_type_ref_id", "ref_type", "ref_id"),)

    id: str = Field(primary_key=True, min_length=1, max_length=36)

    # item_type 限定值："folder" | "note_ref"（业务校验在 schema/service 层做）
    item_type: str = Field(index=True, min_length=1, max_length=20)

    # 无限层级：root 为 NULL；不做 DB 级 cascade，递归软删除由 service 实现。
    parent_id: Optional[str] = Field(default=None, index=True, max_length=36)

    # folder 必填；note_ref 允许空字符串（业务层约束），存储层仅限制长度。
    name: str = Field(default="", max_length=500)

    color: Optional[str] = Field(default=None, max_length=64)

    # 引用：用于 note_ref 指向外部资源（允许 ghost；同步时可能先到 ref 后到实体）。
    # ref_type 限定值："flow_note" | "memos_memo"
    ref_type: Optional[str] = Field(default=None, max_length=50)
    ref_id: Optional[str] = Field(default=None, max_length=128)

    sort_order: int = Field(default=0, index=True)
