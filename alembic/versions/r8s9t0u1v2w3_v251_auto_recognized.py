"""v0.25.1: auto_recognized flag on documents

Revision ID: r8s9t0u1v2w3
Revises: p6q7r8s9t0u1
Create Date: 2026-07-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "r8s9t0u1v2w3"
down_revision: Union[str, Sequence[str], None] = "p6q7r8s9t0u1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(inspector, table: str) -> set[str]:
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "documents" not in inspector.get_table_names():
        return
    columns = _column_names(inspector, "documents")
    if "auto_recognized" not in columns:
        op.add_column(
            "documents",
            sa.Column("auto_recognized", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "documents" not in inspector.get_table_names():
        return
    columns = _column_names(inspector, "documents")
    if "auto_recognized" in columns:
        op.drop_column("documents", "auto_recognized")
