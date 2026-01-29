"""track user devices and login IPs

Revision ID: 20260128_0003
Revises: 20260127_0002
Create Date: 2026-01-28 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260128_0003"
down_revision = "20260127_0002"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    if not _table_exists("user_devices"):
        op.create_table(
            "user_devices",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("device_id", sa.String(length=128), nullable=False),
            sa.Column("device_name", sa.String(length=200), nullable=True),
            sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_ip", sa.String(length=64), nullable=True),
            sa.Column("last_user_agent", sa.Text(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "user_id",
                "device_id",
                name="uq_user_devices_user_id_device_id",
            ),
        )
        op.create_index("ix_user_devices_user_id", "user_devices", ["user_id"], unique=False)
        op.create_index("ix_user_devices_device_id", "user_devices", ["device_id"], unique=False)
        op.create_index("ix_user_devices_first_seen", "user_devices", ["first_seen"], unique=False)
        op.create_index("ix_user_devices_last_seen", "user_devices", ["last_seen"], unique=False)
        op.create_index("ix_user_devices_last_ip", "user_devices", ["last_ip"], unique=False)
        op.create_index("ix_user_devices_revoked_at", "user_devices", ["revoked_at"], unique=False)
        op.create_index("ix_user_devices_created_at", "user_devices", ["created_at"], unique=False)
        op.create_index("ix_user_devices_updated_at", "user_devices", ["updated_at"], unique=False)

    if not _table_exists("user_device_ips"):
        op.create_table(
            "user_device_ips",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("device_id", sa.String(length=128), nullable=False),
            sa.Column("ip", sa.String(length=64), nullable=False),
            sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "user_id",
                "device_id",
                "ip",
                name="uq_user_device_ips_user_id_device_id_ip",
            ),
        )
        op.create_index("ix_user_device_ips_user_id", "user_device_ips", ["user_id"], unique=False)
        op.create_index(
            "ix_user_device_ips_device_id", "user_device_ips", ["device_id"], unique=False
        )
        op.create_index("ix_user_device_ips_ip", "user_device_ips", ["ip"], unique=False)
        op.create_index(
            "ix_user_device_ips_first_seen", "user_device_ips", ["first_seen"], unique=False
        )
        op.create_index(
            "ix_user_device_ips_last_seen", "user_device_ips", ["last_seen"], unique=False
        )
        op.create_index(
            "ix_user_device_ips_created_at", "user_device_ips", ["created_at"], unique=False
        )
        op.create_index(
            "ix_user_device_ips_updated_at", "user_device_ips", ["updated_at"], unique=False
        )


def downgrade() -> None:
    # 注意：生产环境不建议轻易 downgrade；这里提供最小实现
    if _table_exists("user_device_ips"):
        op.drop_table("user_device_ips")
    if _table_exists("user_devices"):
        op.drop_table("user_devices")
