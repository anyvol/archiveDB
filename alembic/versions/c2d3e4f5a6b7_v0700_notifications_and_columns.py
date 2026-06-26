"""v0.700: notifications and column preferences

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-06-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import ENUM


revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EVENT_TYPE_NAME = "notificationeventtype"
EVENT_TYPE_VALUES = ("upload", "status_change", "document_edit")


def _column_names(inspector, table: str) -> set[str]:
    return {col["name"] for col in inspector.get_columns(table)}


def _index_names(inspector, table: str) -> set[str]:
    return {idx["name"] for idx in inspector.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "users" in tables:
        user_columns = _column_names(inspector, "users")
        if "visible_columns" not in user_columns:
            op.add_column("users", sa.Column("visible_columns", sa.JSON(), nullable=True))

    event_enum = ENUM(*EVENT_TYPE_VALUES, name=EVENT_TYPE_NAME)
    event_enum.create(bind, checkfirst=True)

    event_enum_no_create = ENUM(*EVENT_TYPE_VALUES, name=EVENT_TYPE_NAME, create_type=False)

    if "notifications" not in tables:
        op.create_table(
            "notifications",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=True),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("event_type", event_enum_no_create, nullable=False),
        )
        inspector = inspect(bind)
        notification_indexes = _index_names(inspector, "notifications")
        if "ix_notifications_user_id" not in notification_indexes:
            op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
        if "ix_notifications_user_unread" not in notification_indexes:
            op.create_index(
                "ix_notifications_user_unread",
                "notifications",
                ["user_id", "is_read", "created_at"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "notifications" in tables:
        notification_indexes = _index_names(inspector, "notifications")
        if "ix_notifications_user_unread" in notification_indexes:
            op.drop_index("ix_notifications_user_unread", table_name="notifications")
        if "ix_notifications_user_id" in notification_indexes:
            op.drop_index("ix_notifications_user_id", table_name="notifications")
        op.drop_table("notifications")

    ENUM(*EVENT_TYPE_VALUES, name=EVENT_TYPE_NAME).drop(bind, checkfirst=True)

    if "users" in tables:
        user_columns = _column_names(inspector, "users")
        if "visible_columns" in user_columns:
            op.drop_column("users", "visible_columns")
