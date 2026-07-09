"""v0.20.0: archive notifications, orders, project establishing order

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-07-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "l2m3n4o5p6q7"
down_revision: Union[str, Sequence[str], None] = "k1l2m3n4o5p6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(inspector, table: str) -> bool:
    return table in set(inspector.get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not _table_exists(inspector, "archive_orders"):
        op.create_table(
            "archive_orders",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("number", sa.String(64), nullable=False, unique=True, index=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("order_date", sa.DateTime(), nullable=False),
            sa.Column("file_name", sa.String(), nullable=False),
            sa.Column("file_path", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        )

    if not _table_exists(inspector, "archive_notifications"):
        op.create_table(
            "archive_notifications",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("number", sa.String(64), nullable=False, unique=True, index=True),
            sa.Column("change_number", sa.String(64), nullable=False),
            sa.Column("change_date", sa.DateTime(), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False, index=True),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False, index=True),
            sa.Column("file_name", sa.String(), nullable=False),
            sa.Column("file_path", sa.String(), nullable=False),
            sa.Column("developer_signed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("reviewer_signed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("approver_signed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        )

    change_cols = {col["name"] for col in inspector.get_columns("change_notifications")}
    if "archive_notification_id" not in change_cols:
        op.add_column(
            "change_notifications",
            sa.Column(
                "archive_notification_id",
                sa.Integer(),
                sa.ForeignKey("archive_notifications.id"),
                nullable=True,
                index=True,
            ),
        )

    project_cols = {col["name"] for col in inspector.get_columns("projects")}
    if "establishing_order_id" not in project_cols:
        op.add_column(
            "projects",
            sa.Column(
                "establishing_order_id",
                sa.Integer(),
                sa.ForeignKey("archive_orders.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "projects" in tables:
        project_cols = {col["name"] for col in inspector.get_columns("projects")}
        if "establishing_order_id" in project_cols:
            op.drop_column("projects", "establishing_order_id")

    if "change_notifications" in tables:
        change_cols = {col["name"] for col in inspector.get_columns("change_notifications")}
        if "archive_notification_id" in change_cols:
            op.drop_column("change_notifications", "archive_notification_id")

    if "archive_notifications" in tables:
        op.drop_table("archive_notifications")
    if "archive_orders" in tables:
        op.drop_table("archive_orders")
