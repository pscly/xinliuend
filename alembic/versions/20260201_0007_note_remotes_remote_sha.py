"""store remote memo sha256 on note_remotes

Revision ID: 20260201_0007
Revises: 20260201_0006
Create Date: 2026-02-01 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260201_0007"
down_revision = "20260201_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "note_remotes",
        sa.Column(
            "remote_sha256_hex",
            sa.String(length=64),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("note_remotes", "remote_sha256_hex")
