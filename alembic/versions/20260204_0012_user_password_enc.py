"""user password encrypted

Revision ID: 20260204_0012
Revises: 20260203_0011
Create Date: 2026-02-04 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260204_0012"
down_revision = "20260203_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_enc", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "password_enc")

