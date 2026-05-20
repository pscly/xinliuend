"""add memos_user_name to users

Revision ID: 20260519_0015
Revises: 20260517_0015
Create Date: 2026-05-19 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260519_0015"
down_revision = "20260517_0015"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return table_name in insp.get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return any(col.get("name") == column_name for col in insp.get_columns(table_name))


def upgrade() -> None:
    if not _table_exists("users"):
        return
    if not _column_exists("users", "memos_user_name"):
        op.add_column("users", sa.Column("memos_user_name", sa.Text(), nullable=True))


def downgrade() -> None:
    if not _table_exists("users"):
        return
    if _column_exists("users", "memos_user_name"):
        op.drop_column("users", "memos_user_name")
