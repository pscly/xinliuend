"""collection items (collections/jinnang)

Revision ID: 20260211_0013
Revises: 20260204_0012
Create Date: 2026-02-11 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260211_0013"
down_revision = "20260204_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collection_items",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("item_type", sa.String(length=20), nullable=False),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=500), nullable=False, server_default=sa.text("''")),
        sa.Column("color", sa.String(length=64), nullable=True),
        sa.Column("ref_type", sa.String(length=50), nullable=True),
        sa.Column("ref_id", sa.String(length=128), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "client_updated_at_ms", sa.BigInteger(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_index("ix_collection_items_user_id", "collection_items", ["user_id"], unique=False)
    op.create_index(
        "ix_collection_items_client_updated_at_ms",
        "collection_items",
        ["client_updated_at_ms"],
        unique=False,
    )
    op.create_index(
        "ix_collection_items_updated_at", "collection_items", ["updated_at"], unique=False
    )
    op.create_index(
        "ix_collection_items_deleted_at", "collection_items", ["deleted_at"], unique=False
    )

    op.create_index(
        "ix_collection_items_parent_id", "collection_items", ["parent_id"], unique=False
    )
    op.create_index(
        "ix_collection_items_item_type", "collection_items", ["item_type"], unique=False
    )
    op.create_index(
        "ix_collection_items_sort_order", "collection_items", ["sort_order"], unique=False
    )
    op.create_index(
        "ix_collection_items_ref_type_ref_id",
        "collection_items",
        ["ref_type", "ref_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_collection_items_ref_type_ref_id", table_name="collection_items")
    op.drop_index("ix_collection_items_sort_order", table_name="collection_items")
    op.drop_index("ix_collection_items_item_type", table_name="collection_items")
    op.drop_index("ix_collection_items_parent_id", table_name="collection_items")
    op.drop_index("ix_collection_items_deleted_at", table_name="collection_items")
    op.drop_index("ix_collection_items_updated_at", table_name="collection_items")
    op.drop_index("ix_collection_items_client_updated_at_ms", table_name="collection_items")
    op.drop_index("ix_collection_items_user_id", table_name="collection_items")
    op.drop_table("collection_items")
