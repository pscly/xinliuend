"""init schema (users + settings + todo + sync)

Revision ID: 20260124_0001
Revises: None
Create Date: 2026-01-24 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260124_0001"
down_revision = None
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    if not _table_exists("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("username", sa.String(length=64), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("memos_id", sa.Integer(), nullable=True),
            sa.Column("memos_token", sa.Text(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_users_username", "users", ["username"], unique=True)
        op.create_index("ix_users_memos_id", "users", ["memos_id"], unique=False)
        op.create_index("ix_users_is_active", "users", ["is_active"], unique=False)
        op.create_index("ix_users_created_at", "users", ["created_at"], unique=False)
        op.create_index("ix_users_memos_token", "users", ["memos_token"], unique=False)

    if not _table_exists("user_settings"):
        op.create_table(
            "user_settings",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("key", sa.String(length=128), nullable=False),
            sa.Column("value_json", sa.JSON(), nullable=False),
            sa.Column("client_updated_at_ms", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "key", name="uq_user_settings_user_id_key"),
        )
        op.create_index("ix_user_settings_user_id", "user_settings", ["user_id"], unique=False)
        op.create_index("ix_user_settings_key", "user_settings", ["key"], unique=False)
        op.create_index("ix_user_settings_deleted_at", "user_settings", ["deleted_at"], unique=False)
        op.create_index("ix_user_settings_updated_at", "user_settings", ["updated_at"], unique=False)

    if not _table_exists("todo_lists"):
        op.create_table(
            "todo_lists",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("color", sa.String(length=32), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("client_updated_at_ms", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_todo_lists_user_id", "todo_lists", ["user_id"], unique=False)
        op.create_index("ix_todo_lists_archived", "todo_lists", ["archived"], unique=False)
        op.create_index("ix_todo_lists_deleted_at", "todo_lists", ["deleted_at"], unique=False)
        op.create_index("ix_todo_lists_sort_order", "todo_lists", ["sort_order"], unique=False)
        op.create_index("ix_todo_lists_updated_at", "todo_lists", ["updated_at"], unique=False)

    if not _table_exists("todo_items"):
        op.create_table(
            "todo_items",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("list_id", sa.String(length=36), sa.ForeignKey("todo_lists.id"), nullable=False),
            sa.Column("parent_id", sa.String(length=36), sa.ForeignKey("todo_items.id"), nullable=True),
            sa.Column("title", sa.String(length=500), nullable=False),
            sa.Column("note", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'open'")),
            sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("due_at_local", sa.String(length=19), nullable=True),
            sa.Column("completed_at_local", sa.String(length=19), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("tags_json", sa.JSON(), nullable=False),
            sa.Column("is_recurring", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("rrule", sa.String(length=512), nullable=True),
            sa.Column("dtstart_local", sa.String(length=19), nullable=True),
            sa.Column("tzid", sa.String(length=64), nullable=False, server_default=sa.text("'Asia/Shanghai'")),
            sa.Column("reminders_json", sa.JSON(), nullable=False),
            sa.Column("client_updated_at_ms", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_todo_items_user_id", "todo_items", ["user_id"], unique=False)
        op.create_index("ix_todo_items_list_id", "todo_items", ["list_id"], unique=False)
        op.create_index("ix_todo_items_parent_id", "todo_items", ["parent_id"], unique=False)
        op.create_index("ix_todo_items_status", "todo_items", ["status"], unique=False)
        op.create_index("ix_todo_items_is_recurring", "todo_items", ["is_recurring"], unique=False)
        op.create_index("ix_todo_items_deleted_at", "todo_items", ["deleted_at"], unique=False)
        op.create_index("ix_todo_items_updated_at", "todo_items", ["updated_at"], unique=False)
        op.create_index("ix_todo_items_sort_order", "todo_items", ["sort_order"], unique=False)

    if not _table_exists("todo_item_occurrences"):
        op.create_table(
            "todo_item_occurrences",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("item_id", sa.String(length=36), sa.ForeignKey("todo_items.id"), nullable=False),
            sa.Column("tzid", sa.String(length=64), nullable=False, server_default=sa.text("'Asia/Shanghai'")),
            sa.Column("recurrence_id_local", sa.String(length=19), nullable=False),
            sa.Column("status_override", sa.String(length=20), nullable=True),
            sa.Column("title_override", sa.String(length=500), nullable=True),
            sa.Column("note_override", sa.Text(), nullable=True),
            sa.Column("due_at_override_local", sa.String(length=19), nullable=True),
            sa.Column("completed_at_local", sa.String(length=19), nullable=True),
            sa.Column("client_updated_at_ms", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "user_id",
                "item_id",
                "tzid",
                "recurrence_id_local",
                name="uq_todo_occurrence_user_item_tz_recur",
            ),
        )
        op.create_index("ix_todo_occ_user_id", "todo_item_occurrences", ["user_id"], unique=False)
        op.create_index("ix_todo_occ_item_id", "todo_item_occurrences", ["item_id"], unique=False)
        op.create_index(
            "ix_todo_occ_recurrence_id_local", "todo_item_occurrences", ["recurrence_id_local"], unique=False
        )
        op.create_index("ix_todo_occ_deleted_at", "todo_item_occurrences", ["deleted_at"], unique=False)
        op.create_index("ix_todo_occ_updated_at", "todo_item_occurrences", ["updated_at"], unique=False)

    if not _table_exists("sync_events"):
        op.create_table(
            "sync_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("resource", sa.String(length=50), nullable=False),
            sa.Column("entity_id", sa.String(length=128), nullable=False),
            sa.Column("action", sa.String(length=20), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_sync_events_user_id", "sync_events", ["user_id"], unique=False)
        op.create_index("ix_sync_events_resource", "sync_events", ["resource"], unique=False)
        op.create_index("ix_sync_events_entity_id", "sync_events", ["entity_id"], unique=False)
        op.create_index("ix_sync_events_created_at", "sync_events", ["created_at"], unique=False)


def downgrade() -> None:
    # 注意：生产环境不建议轻易 downgrade；这里提供最小实现
    for name in [
        "sync_events",
        "todo_item_occurrences",
        "todo_items",
        "todo_lists",
        "user_settings",
    ]:
        if _table_exists(name):
            op.drop_table(name)
