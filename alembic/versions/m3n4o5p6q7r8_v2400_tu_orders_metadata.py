"""v0.24.0: archive technical specs, order project/products, project establishing TU

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-07-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "m3n4o5p6q7r8"
down_revision: Union[str, Sequence[str], None] = "l2m3n4o5p6q7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(inspector, table: str) -> bool:
    return table in set(inspector.get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not _table_exists(inspector, "archive_technical_specs"):
        op.create_table(
            "archive_technical_specs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("number", sa.String(64), nullable=False, unique=True, index=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("okpd2", sa.String(32), nullable=False),
            sa.Column("product_index", sa.String(8), nullable=False),
            sa.Column("okpo", sa.String(8), nullable=False),
            sa.Column("year", sa.Integer(), nullable=False),
            sa.Column("file_name", sa.String(), nullable=False),
            sa.Column("file_path", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        )

    order_cols = {col["name"] for col in inspector.get_columns("archive_orders")}
    if "project_id" not in order_cols:
        op.add_column(
            "archive_orders",
            sa.Column(
                "project_id",
                sa.Integer(),
                sa.ForeignKey("projects.id", ondelete="SET NULL"),
                nullable=True,
                index=True,
            ),
        )

    if not _table_exists(inspector, "archive_order_products"):
        op.create_table(
            "archive_order_products",
            sa.Column(
                "order_id",
                sa.Integer(),
                sa.ForeignKey("archive_orders.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column(
                "product_id",
                sa.Integer(),
                sa.ForeignKey("products.id", ondelete="CASCADE"),
                primary_key=True,
            ),
        )

    project_cols = {col["name"] for col in inspector.get_columns("projects")}
    if "establishing_tu_id" not in project_cols:
        op.add_column(
            "projects",
            sa.Column(
                "establishing_tu_id",
                sa.Integer(),
                sa.ForeignKey("archive_technical_specs.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "projects" in tables:
        project_cols = {col["name"] for col in inspector.get_columns("projects")}
        if "establishing_tu_id" in project_cols:
            op.drop_column("projects", "establishing_tu_id")

    if "archive_order_products" in tables:
        op.drop_table("archive_order_products")

    if "archive_orders" in tables:
        order_cols = {col["name"] for col in inspector.get_columns("archive_orders")}
        if "project_id" in order_cols:
            op.drop_column("archive_orders", "project_id")

    if "archive_technical_specs" in tables:
        op.drop_table("archive_technical_specs")
