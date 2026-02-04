from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, Text, UniqueConstraint
from sqlalchemy.types import JSON as SAJSON
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


class Note(TenantRowBase, table=True):
    __tablename__ = "notes"  # pyright: ignore[reportAssignmentType]

    id: str = Field(primary_key=True, min_length=1, max_length=36)

    title: str = Field(default="", max_length=500)
    body_md: str = Field(default="", sa_column=Column(Text, nullable=False))

    pinned: bool = Field(default=False, index=True)
    archived: bool = Field(default=False, index=True)


class Tag(TenantRowBase, table=True):
    __tablename__ = "tags"  # pyright: ignore[reportAssignmentType]

    __table_args__ = (UniqueConstraint("user_id", "name_lower", name="uq_tags_user_id_name_lower"),)

    id: str = Field(primary_key=True, min_length=1, max_length=36)

    # Preserve user input as-is for display; use name_lower for uniqueness.
    name_original: str = Field(min_length=1, max_length=200)
    name_lower: str = Field(min_length=1, max_length=200, index=True)


class NoteTag(TenantRowBase, table=True):
    __tablename__ = "note_tags"  # pyright: ignore[reportAssignmentType]

    __table_args__ = (
        UniqueConstraint("user_id", "note_id", "tag_id", name="uq_note_tags_user_note_tag"),
    )

    id: str = Field(primary_key=True, min_length=1, max_length=36)

    note_id: str = Field(index=True, foreign_key="notes.id", min_length=1, max_length=36)
    tag_id: str = Field(index=True, foreign_key="tags.id", min_length=1, max_length=36)


class NoteRevision(TenantRowBase, table=True):
    __tablename__ = "note_revisions"  # pyright: ignore[reportAssignmentType]

    id: str = Field(primary_key=True, min_length=1, max_length=36)
    note_id: str = Field(index=True, foreign_key="notes.id", min_length=1, max_length=36)

    # NORMAL: regular snapshots; CONFLICT: preserved local snapshot when remote wins.
    kind: str = Field(default="NORMAL", max_length=20, index=True)
    reason: Optional[str] = Field(default=None, max_length=500)

    # Snapshot schema (contract): {title, body_md, tags, client_updated_at_ms}
    snapshot_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(SAJSON))


class NoteShare(TenantRowBase, table=True):
    __tablename__ = "note_shares"  # pyright: ignore[reportAssignmentType]

    __table_args__ = (
        UniqueConstraint("user_id", "token_hmac_hex", name="uq_note_shares_user_id_token_hmac"),
    )

    id: str = Field(primary_key=True, min_length=1, max_length=36)
    note_id: str = Field(index=True, foreign_key="notes.id", min_length=1, max_length=36)

    # NEVER store plaintext share tokens.
    token_prefix: str = Field(min_length=1, max_length=32, index=True)
    token_hmac_hex: str = Field(min_length=1, max_length=128)

    expires_at: Optional[datetime] = Field(default=None, index=True)
    revoked_at: Optional[datetime] = Field(default=None, index=True)

    # Public share comments governance (per-share).
    # Default: anonymous comments disabled.
    allow_anonymous_comments: bool = Field(default=False, index=True)
    anonymous_comments_require_captcha: bool = Field(default=True, index=True)


class PublicShareComment(TenantRowBase, table=True):
    __tablename__ = "public_share_comments"  # pyright: ignore[reportAssignmentType]

    id: str = Field(primary_key=True, min_length=1, max_length=36)
    share_id: str = Field(index=True, foreign_key="note_shares.id", min_length=1, max_length=36)

    body: str = Field(default="", sa_column=Column(Text, nullable=False))
    author_name: Optional[str] = Field(default=None, max_length=100)
    attachment_ids_json: list[str] = Field(default_factory=list, sa_column=Column(SAJSON))

    is_folded: bool = Field(default=False, index=True)
    folded_at: Optional[datetime] = Field(default=None, index=True)
    folded_reason: Optional[str] = Field(default=None, max_length=200)
    reported_count: int = Field(default=0)


class Attachment(TenantRowBase, table=True):
    __tablename__ = "attachments"  # pyright: ignore[reportAssignmentType]

    __table_args__ = (
        UniqueConstraint("user_id", "storage_key", name="uq_attachments_user_id_storage_key"),
    )

    id: str = Field(primary_key=True, min_length=1, max_length=36)

    # Metadata-only. Binary content lives in external storage.
    storage_key: str = Field(min_length=1, max_length=512, index=True)
    filename: Optional[str] = Field(default=None, max_length=255)
    content_type: Optional[str] = Field(default=None, max_length=255)
    size_bytes: int = Field(default=0)
    sha256_hex: Optional[str] = Field(default=None, max_length=64)


class NoteAttachment(TenantRowBase, table=True):
    __tablename__ = "note_attachments"  # pyright: ignore[reportAssignmentType]

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "note_id",
            "attachment_id",
            name="uq_note_attachments_user_note_attachment",
        ),
    )

    id: str = Field(primary_key=True, min_length=1, max_length=36)
    note_id: str = Field(index=True, foreign_key="notes.id", min_length=1, max_length=36)
    attachment_id: str = Field(
        index=True, foreign_key="attachments.id", min_length=1, max_length=36
    )


class NoteRemote(TenantRowBase, table=True):
    __tablename__ = "note_remotes"  # pyright: ignore[reportAssignmentType]

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "provider",
            "remote_id",
            name="uq_note_remotes_user_provider_remote_id",
        ),
    )

    id: str = Field(primary_key=True, min_length=1, max_length=36)
    note_id: str = Field(index=True, foreign_key="notes.id", min_length=1, max_length=36)

    provider: str = Field(min_length=1, max_length=50)
    remote_id: str = Field(min_length=1, max_length=200)

    # Used to detect remote/local divergence without relying on clock sync.
    remote_sha256_hex: Optional[str] = Field(default=None, max_length=64)
