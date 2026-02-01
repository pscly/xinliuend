"""add kind/reason to note_revisions

Revision ID: 20260201_0006
Revises: 20260201_0005
Create Date: 2026-02-01 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260201_0006"
down_revision = "20260201_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "note_revisions",
        sa.Column(
            "kind",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'NORMAL'"),
        ),
    )
    op.add_column(
        "note_revisions",
        sa.Column(
            "reason",
            sa.String(length=500),
            nullable=True,
        ),
    )
    op.create_index("ix_note_revisions_kind", "note_revisions", ["kind"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_note_revisions_kind", table_name="note_revisions")
    op.drop_column("note_revisions", "reason")
    op.drop_column("note_revisions", "kind")
