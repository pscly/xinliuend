"""user email + email_verified_at + password_changed_at + reset/verify token tables

Revision ID: 20260517_0015
Revises: 20260510_0014
Create Date: 2026-05-17 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260517_0015"
down_revision = "20260510_0014"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return any(c["name"] == column_name for c in insp.get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return any(idx.get("name") == index_name for idx in insp.get_indexes(table_name))


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    # 1) Add new columns to users.
    if _has_table("users"):
        if not _has_column("users", "email"):
            op.add_column("users", sa.Column("email", sa.String(length=320), nullable=True))
        if not _has_column("users", "email_verified_at"):
            op.add_column(
                "users",
                sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
            )
        if not _has_column("users", "password_changed_at"):
            # Default existing rows to NULL — verify_user_session treats NULL as
            # "no constraint" so existing sessions stay valid.
            op.add_column(
                "users",
                sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
            )

        if not _has_index("users", "uq_users_email_not_null"):
            op.create_index(
                "uq_users_email_not_null",
                "users",
                ["email"],
                unique=True,
                postgresql_where=sa.text("email IS NOT NULL"),
                sqlite_where=sa.text("email IS NOT NULL"),
            )

    # 2) Email verification tokens (for binding an email to a user account).
    if not _has_table("email_verification_tokens"):
        op.create_table(
            "email_verification_tokens",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("email", sa.String(length=320), nullable=False, index=True),
            sa.Column("code_hash", sa.String(length=128), nullable=False, index=True),
            sa.Column("purpose", sa.String(length=32), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ip", sa.String(length=64), nullable=True),
        )

    # 3) Password reset tokens (forgot-password flow).
    if not _has_table("password_reset_tokens"):
        op.create_table(
            "password_reset_tokens",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("token_hash", sa.String(length=128), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("requester_ip", sa.String(length=64), nullable=True),
            sa.Column("requester_ua", sa.Text(), nullable=True),
        )
        op.create_index(
            "uq_password_reset_tokens_token_hash",
            "password_reset_tokens",
            ["token_hash"],
            unique=True,
        )

    # 4) Site-wide admin-editable settings (e.g. SMTP).
    if not _has_table("site_settings"):
        op.create_table(
            "site_settings",
            sa.Column("key", sa.String(length=128), primary_key=True),
            sa.Column("value_json", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_by", sa.String(length=64), nullable=True),
        )


def downgrade() -> None:
    if _has_table("site_settings"):
        op.drop_table("site_settings")

    if _has_table("password_reset_tokens"):
        if _has_index("password_reset_tokens", "uq_password_reset_tokens_token_hash"):
            op.drop_index(
                "uq_password_reset_tokens_token_hash",
                table_name="password_reset_tokens",
            )
        op.drop_table("password_reset_tokens")

    if _has_table("email_verification_tokens"):
        op.drop_table("email_verification_tokens")

    if _has_table("users"):
        if _has_index("users", "uq_users_email_not_null"):
            op.drop_index("uq_users_email_not_null", table_name="users")
        for col in ("password_changed_at", "email_verified_at", "email"):
            if _has_column("users", col):
                op.drop_column("users", col)
