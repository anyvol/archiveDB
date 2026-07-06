"""v0.14.0: admin access codes, user access_granted flag

Revision ID: g7h8i9j0k1l2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-06 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "g7h8i9j0k1l2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(inspector, table: str) -> set[str]:
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "users" in tables:
        user_columns = _column_names(inspector, "users")
        if "access_granted" not in user_columns:
            op.add_column(
                "users",
                sa.Column("access_granted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            )
            op.execute(
                """
                UPDATE users
                SET access_granted = true
                WHERE email_verified = true OR role::text IN ('admin', 'master_admin', 'reviewer')
                """
            )

    if "admin_access_codes" not in tables:
        op.create_table(
            "admin_access_codes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("code_hash", sa.String(64), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("used_at", sa.DateTime(), nullable=True),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_admin_access_codes_user_id", "admin_access_codes", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "admin_access_codes" in tables:
        op.drop_index("ix_admin_access_codes_user_id", table_name="admin_access_codes")
        op.drop_table("admin_access_codes")

    if "users" in tables:
        user_columns = _column_names(inspector, "users")
        if "access_granted" in user_columns:
            op.drop_column("users", "access_granted")
