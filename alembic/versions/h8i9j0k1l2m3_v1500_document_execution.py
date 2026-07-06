"""v0.15.0: document execution suffix

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-07-06 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "h8i9j0k1l2m3"
down_revision: Union[str, Sequence[str], None] = "g7h8i9j0k1l2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(inspector, table: str) -> set[str]:
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "design_documents" in tables:
        columns = _column_names(inspector, "design_documents")
        if "execution" not in columns:
            op.add_column("design_documents", sa.Column("execution", sa.String(length=4), nullable=True))

    if "tech_documents" in tables:
        columns = _column_names(inspector, "tech_documents")
        if "execution" not in columns:
            op.add_column("tech_documents", sa.Column("execution", sa.String(length=4), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "design_documents" in tables:
        columns = _column_names(inspector, "design_documents")
        if "execution" in columns:
            op.drop_column("design_documents", "execution")

    if "tech_documents" in tables:
        columns = _column_names(inspector, "tech_documents")
        if "execution" in columns:
            op.drop_column("tech_documents", "execution")
