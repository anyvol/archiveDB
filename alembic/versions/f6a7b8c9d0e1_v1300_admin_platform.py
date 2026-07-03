"""v0.13.0: master_admin, email verification, system settings, backups

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-03 07:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(inspector, table: str) -> set[str]:
    return {col["name"] for col in inspector.get_columns(table)}


def _enum_values(bind, enum_name: str) -> set[str]:
    rows = bind.execute(
        text(
            """
            SELECT e.enumlabel
            FROM pg_enum e
            JOIN pg_type t ON e.enumtypid = t.oid
            WHERE t.typname = :enum_name
            """
        ),
        {"enum_name": enum_name},
    ).fetchall()
    return {row[0] for row in rows}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "userrole" not in {t for t in bind.execute(text("SELECT typname FROM pg_type")).scalars()}:
        pass
    else:
        values = _enum_values(bind, "userrole")
        if "master_admin" not in values:
            op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'master_admin' BEFORE 'admin'")

    if "users" in tables:
        user_columns = _column_names(inspector, "users")
        if "email_verified" not in user_columns:
            op.add_column(
                "users",
                sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            )
        if "is_active" not in user_columns:
            op.add_column(
                "users",
                sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            )
        op.execute(
            text(
                """
                UPDATE users
                SET is_active = true,
                    email_verified = CASE WHEN email IS NOT NULL AND trim(email) <> '' THEN true ELSE false END
                """
            )
        )
        op.alter_column("users", "email_verified", server_default=None)
        op.alter_column("users", "is_active", server_default=None)
        indexes = {idx["name"] for idx in inspector.get_indexes("users")}
        if "ix_users_email" not in indexes:
            op.create_index("ix_users_email", "users", ["email"], unique=True)

    if "system_settings" not in tables:
        op.create_table(
            "system_settings",
            sa.Column("key", sa.String(length=64), primary_key=True),
            sa.Column("value", sa.JSON(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        )

    if "email_verification_codes" not in tables:
        op.create_table(
            "email_verification_codes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("code_hash", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_email_verification_codes_user_id", "email_verification_codes", ["user_id"])

    if "password_reset_tokens" not in tables:
        op.create_table(
            "password_reset_tokens",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("used_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])
        op.create_index("ix_password_reset_tokens_token_hash", "password_reset_tokens", ["token_hash"], unique=True)

    if "backup_records" not in tables:
        op.create_table(
            "backup_records",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("backup_id", sa.String(length=64), nullable=False),
            sa.Column("backup_type", sa.String(length=32), nullable=False),
            sa.Column("file_path", sa.String(length=512), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
            sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
            sa.Column("triggered_by", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_backup_records_backup_id", "backup_records", ["backup_id"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "backup_records" in tables:
        op.drop_table("backup_records")
    if "password_reset_tokens" in tables:
        op.drop_table("password_reset_tokens")
    if "email_verification_codes" in tables:
        op.drop_table("email_verification_codes")
    if "system_settings" in tables:
        op.drop_table("system_settings")

    if "users" in tables:
        user_columns = _column_names(inspector, "users")
        indexes = {idx["name"] for idx in inspector.get_indexes("users")}
        if "ix_users_email" in indexes:
            op.drop_index("ix_users_email", table_name="users")
        if "is_active" in user_columns:
            op.drop_column("users", "is_active")
        if "email_verified" in user_columns:
            op.drop_column("users", "email_verified")
