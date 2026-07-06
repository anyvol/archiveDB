"""v0.15.0: remove execution from tech documents

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-07-06 11:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "i9j0k1l2m3n4"
down_revision: Union[str, Sequence[str], None] = "h8i9j0k1l2m3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(inspector, table: str) -> set[str]:
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "tech_documents" in tables:
        columns = _column_names(inspector, "tech_documents")
        if "execution" in columns:
            op.drop_column("tech_documents", "execution")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "tech_documents" in tables:
        columns = _column_names(inspector, "tech_documents")
        if "execution" not in columns:
            op.add_column("tech_documents", sa.Column("execution", sa.String(length=4), nullable=True))
