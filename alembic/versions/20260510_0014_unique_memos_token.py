"""add unique index for non-null memos tokens

Revision ID: 20260510_0014
Revises: 20260211_0013
Create Date: 2026-05-10 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260510_0014"
down_revision = "20260211_0013"
branch_labels = None
depends_on = None


_INDEX_NAME = "uq_users_memos_token_not_null"


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return table_name in insp.get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return any(idx.get("name") == index_name for idx in insp.get_indexes(table_name))


def _assert_no_duplicate_non_null_tokens() -> None:
    bind = op.get_bind()
    duplicates = bind.execute(
        sa.text(
            """
            SELECT memos_token, COUNT(*) AS c
            FROM users
            WHERE memos_token IS NOT NULL AND memos_token <> ''
            GROUP BY memos_token
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).fetchone()
    if duplicates is not None:
        raise RuntimeError(
            "Cannot create unique memos token index: duplicate non-null users.memos_token exists"
        )


def upgrade() -> None:
    if not _table_exists("users"):
        return
    if _index_exists("users", _INDEX_NAME):
        return
    _assert_no_duplicate_non_null_tokens()
    op.create_index(
        _INDEX_NAME,
        "users",
        ["memos_token"],
        unique=True,
        postgresql_where=sa.text("memos_token IS NOT NULL"),
        sqlite_where=sa.text("memos_token IS NOT NULL"),
    )


def downgrade() -> None:
    if not _table_exists("users"):
        return
    if _index_exists("users", _INDEX_NAME):
        op.drop_index(_INDEX_NAME, table_name="users")
