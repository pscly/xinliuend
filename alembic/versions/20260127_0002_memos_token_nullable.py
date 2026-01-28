"""make users.memos_token nullable

Revision ID: 20260127_0002
Revises: 20260124_0001
Create Date: 2026-01-27 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260127_0002"
down_revision = "20260124_0001"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return table_name in insp.get_table_names()


def _column_nullable(table_name: str, column_name: str) -> bool | None:
    bind = op.get_bind()
    insp = inspect(bind)
    for col in insp.get_columns(table_name):
        if col.get("name") == column_name:
            return bool(col.get("nullable"))
    return None


def upgrade() -> None:
    if not _table_exists("users"):
        return
    nullable = _column_nullable("users", "memos_token")
    if nullable is True:
        return
    if nullable is None:
        return
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("memos_token", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    if not _table_exists("users"):
        return
    # downgrade 时尽量避免因 NULL 导致失败
    op.execute(sa.text("UPDATE users SET memos_token = '' WHERE memos_token IS NULL"))
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("memos_token", existing_type=sa.Text(), nullable=False)
