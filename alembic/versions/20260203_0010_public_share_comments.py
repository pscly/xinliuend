"""public share comments + share comment config

Revision ID: 20260203_0010
Revises: 20260202_0009
Create Date: 2026-02-03 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260203_0010"
down_revision = "20260202_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Per-share anonymous comment governance.
    op.add_column(
        "note_shares",
        sa.Column(
            "allow_anonymous_comments",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "note_shares",
        sa.Column(
            "anonymous_comments_require_captcha",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.create_index(
        "ix_note_shares_allow_anonymous_comments",
        "note_shares",
        ["allow_anonymous_comments"],
        unique=False,
    )
    op.create_index(
        "ix_note_shares_anonymous_comments_require_captcha",
        "note_shares",
        ["anonymous_comments_require_captcha"],
        unique=False,
    )

    # Public share comments table (rows are owned by the sharing user; no plaintext token stored).
    op.create_table(
        "public_share_comments",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "share_id",
            sa.String(length=36),
            sa.ForeignKey("note_shares.id"),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author_name", sa.String(length=100), nullable=True),
        sa.Column("attachment_ids_json", sa.JSON(), nullable=False),
        sa.Column(
            "is_folded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("folded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("folded_reason", sa.String(length=200), nullable=True),
        sa.Column(
            "reported_count",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "client_updated_at_ms",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_public_share_comments_user_id",
        "public_share_comments",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_public_share_comments_share_id",
        "public_share_comments",
        ["share_id"],
        unique=False,
    )
    op.create_index(
        "ix_public_share_comments_deleted_at",
        "public_share_comments",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        "ix_public_share_comments_updated_at",
        "public_share_comments",
        ["updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_public_share_comments_is_folded",
        "public_share_comments",
        ["is_folded"],
        unique=False,
    )
    op.create_index(
        "ix_public_share_comments_folded_at",
        "public_share_comments",
        ["folded_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_public_share_comments_folded_at", table_name="public_share_comments")
    op.drop_index("ix_public_share_comments_is_folded", table_name="public_share_comments")
    op.drop_index("ix_public_share_comments_updated_at", table_name="public_share_comments")
    op.drop_index("ix_public_share_comments_deleted_at", table_name="public_share_comments")
    op.drop_index("ix_public_share_comments_share_id", table_name="public_share_comments")
    op.drop_index("ix_public_share_comments_user_id", table_name="public_share_comments")
    op.drop_table("public_share_comments")

    op.drop_index("ix_note_shares_anonymous_comments_require_captcha", table_name="note_shares")
    op.drop_index("ix_note_shares_allow_anonymous_comments", table_name="note_shares")
    op.drop_column("note_shares", "anonymous_comments_require_captcha")
    op.drop_column("note_shares", "allow_anonymous_comments")
