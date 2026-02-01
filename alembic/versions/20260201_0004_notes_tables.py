"""notes schema (notes + tags + revisions + shares + attachments + remotes)

Revision ID: 20260201_0004
Revises: 20260128_0003
Create Date: 2026-02-01 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260201_0004"
down_revision = "20260128_0003"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    if not _table_exists("notes"):
        _ = op.create_table(
            "notes",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("title", sa.String(length=500), nullable=False, server_default=sa.text("''")),
            sa.Column("body_md", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column(
                "client_updated_at_ms", sa.BigInteger(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_notes_user_id", "notes", ["user_id"], unique=False)
        op.create_index("ix_notes_pinned", "notes", ["pinned"], unique=False)
        op.create_index("ix_notes_archived", "notes", ["archived"], unique=False)
        op.create_index("ix_notes_deleted_at", "notes", ["deleted_at"], unique=False)
        op.create_index("ix_notes_updated_at", "notes", ["updated_at"], unique=False)

    if not _table_exists("tags"):
        _ = op.create_table(
            "tags",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("name_original", sa.String(length=200), nullable=False),
            sa.Column("name_lower", sa.String(length=200), nullable=False),
            sa.Column(
                "client_updated_at_ms", sa.BigInteger(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "name_lower", name="uq_tags_user_id_name_lower"),
        )
        op.create_index("ix_tags_user_id", "tags", ["user_id"], unique=False)
        op.create_index("ix_tags_name_lower", "tags", ["name_lower"], unique=False)
        op.create_index("ix_tags_deleted_at", "tags", ["deleted_at"], unique=False)
        op.create_index("ix_tags_updated_at", "tags", ["updated_at"], unique=False)

    if not _table_exists("note_tags"):
        _ = op.create_table(
            "note_tags",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("note_id", sa.String(length=36), sa.ForeignKey("notes.id"), nullable=False),
            sa.Column("tag_id", sa.String(length=36), sa.ForeignKey("tags.id"), nullable=False),
            sa.Column(
                "client_updated_at_ms", sa.BigInteger(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "user_id",
                "note_id",
                "tag_id",
                name="uq_note_tags_user_note_tag",
            ),
        )
        op.create_index("ix_note_tags_user_id", "note_tags", ["user_id"], unique=False)
        op.create_index("ix_note_tags_note_id", "note_tags", ["note_id"], unique=False)
        op.create_index("ix_note_tags_tag_id", "note_tags", ["tag_id"], unique=False)
        op.create_index("ix_note_tags_deleted_at", "note_tags", ["deleted_at"], unique=False)
        op.create_index("ix_note_tags_updated_at", "note_tags", ["updated_at"], unique=False)

    if not _table_exists("note_revisions"):
        _ = op.create_table(
            "note_revisions",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("note_id", sa.String(length=36), sa.ForeignKey("notes.id"), nullable=False),
            sa.Column("snapshot_json", sa.JSON(), nullable=False),
            sa.Column(
                "client_updated_at_ms", sa.BigInteger(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_note_revisions_user_id", "note_revisions", ["user_id"], unique=False)
        op.create_index("ix_note_revisions_note_id", "note_revisions", ["note_id"], unique=False)
        op.create_index(
            "ix_note_revisions_deleted_at", "note_revisions", ["deleted_at"], unique=False
        )
        op.create_index(
            "ix_note_revisions_updated_at", "note_revisions", ["updated_at"], unique=False
        )

    if not _table_exists("note_shares"):
        _ = op.create_table(
            "note_shares",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("note_id", sa.String(length=36), sa.ForeignKey("notes.id"), nullable=False),
            sa.Column("token_prefix", sa.String(length=32), nullable=False),
            sa.Column("token_hmac_hex", sa.String(length=128), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "client_updated_at_ms", sa.BigInteger(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "user_id",
                "token_hmac_hex",
                name="uq_note_shares_user_id_token_hmac",
            ),
        )
        op.create_index("ix_note_shares_user_id", "note_shares", ["user_id"], unique=False)
        op.create_index("ix_note_shares_note_id", "note_shares", ["note_id"], unique=False)
        op.create_index(
            "ix_note_shares_token_prefix", "note_shares", ["token_prefix"], unique=False
        )
        op.create_index("ix_note_shares_expires_at", "note_shares", ["expires_at"], unique=False)
        op.create_index("ix_note_shares_revoked_at", "note_shares", ["revoked_at"], unique=False)
        op.create_index("ix_note_shares_deleted_at", "note_shares", ["deleted_at"], unique=False)
        op.create_index("ix_note_shares_updated_at", "note_shares", ["updated_at"], unique=False)

    if not _table_exists("attachments"):
        _ = op.create_table(
            "attachments",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("storage_key", sa.String(length=512), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=True),
            sa.Column("content_type", sa.String(length=255), nullable=True),
            sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
            sa.Column("sha256_hex", sa.String(length=64), nullable=True),
            sa.Column(
                "client_updated_at_ms", sa.BigInteger(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "user_id",
                "storage_key",
                name="uq_attachments_user_id_storage_key",
            ),
        )
        op.create_index("ix_attachments_user_id", "attachments", ["user_id"], unique=False)
        op.create_index("ix_attachments_storage_key", "attachments", ["storage_key"], unique=False)
        op.create_index("ix_attachments_deleted_at", "attachments", ["deleted_at"], unique=False)
        op.create_index("ix_attachments_updated_at", "attachments", ["updated_at"], unique=False)

    if not _table_exists("note_attachments"):
        _ = op.create_table(
            "note_attachments",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("note_id", sa.String(length=36), sa.ForeignKey("notes.id"), nullable=False),
            sa.Column(
                "attachment_id",
                sa.String(length=36),
                sa.ForeignKey("attachments.id"),
                nullable=False,
            ),
            sa.Column(
                "client_updated_at_ms", sa.BigInteger(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "user_id",
                "note_id",
                "attachment_id",
                name="uq_note_attachments_user_note_attachment",
            ),
        )
        op.create_index(
            "ix_note_attachments_user_id", "note_attachments", ["user_id"], unique=False
        )
        op.create_index(
            "ix_note_attachments_note_id", "note_attachments", ["note_id"], unique=False
        )
        op.create_index(
            "ix_note_attachments_attachment_id",
            "note_attachments",
            ["attachment_id"],
            unique=False,
        )
        op.create_index(
            "ix_note_attachments_deleted_at", "note_attachments", ["deleted_at"], unique=False
        )
        op.create_index(
            "ix_note_attachments_updated_at", "note_attachments", ["updated_at"], unique=False
        )

    if not _table_exists("note_remotes"):
        _ = op.create_table(
            "note_remotes",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("note_id", sa.String(length=36), sa.ForeignKey("notes.id"), nullable=False),
            sa.Column("provider", sa.String(length=50), nullable=False),
            sa.Column("remote_id", sa.String(length=200), nullable=False),
            sa.Column(
                "client_updated_at_ms", sa.BigInteger(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "user_id",
                "provider",
                "remote_id",
                name="uq_note_remotes_user_provider_remote_id",
            ),
        )
        op.create_index("ix_note_remotes_user_id", "note_remotes", ["user_id"], unique=False)
        op.create_index("ix_note_remotes_note_id", "note_remotes", ["note_id"], unique=False)
        op.create_index("ix_note_remotes_deleted_at", "note_remotes", ["deleted_at"], unique=False)
        op.create_index("ix_note_remotes_updated_at", "note_remotes", ["updated_at"], unique=False)


def downgrade() -> None:
    # 注意：生产环境不建议轻易 downgrade；这里提供最小实现
    for name in [
        "note_remotes",
        "note_attachments",
        "attachments",
        "note_shares",
        "note_revisions",
        "note_tags",
        "tags",
        "notes",
    ]:
        if _table_exists(name):
            op.drop_table(name)
