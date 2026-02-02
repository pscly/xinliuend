"""add rate_limit_counters

Revision ID: 20260202_0008
Revises: 20260201_0007
Create Date: 2026-02-02 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260202_0008"
down_revision = "20260201_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_counters",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("window_start_ms", sa.BigInteger(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "scope",
            "key",
            "window_start_ms",
            name="uq_rate_limit_counters_scope_key_window",
        ),
    )
    op.create_index("ix_rate_limit_counters_scope", "rate_limit_counters", ["scope"], unique=False)
    op.create_index("ix_rate_limit_counters_key", "rate_limit_counters", ["key"], unique=False)
    op.create_index(
        "ix_rate_limit_counters_window_start_ms",
        "rate_limit_counters",
        ["window_start_ms"],
        unique=False,
    )
    op.create_index(
        "ix_rate_limit_counters_updated_at",
        "rate_limit_counters",
        ["updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("rate_limit_counters")
