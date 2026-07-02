"""v0.12.0: document metadata fields (reviewer, approver, date)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-02 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(inspector, table: str) -> set[str]:
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "documents" not in inspector.get_table_names():
        return

    doc_columns = _column_names(inspector, "documents")
    if "reviewed_by" not in doc_columns:
        op.add_column("documents", sa.Column("reviewed_by", sa.String(), nullable=True))
    if "approved_by" not in doc_columns:
        op.add_column("documents", sa.Column("approved_by", sa.String(), nullable=True))
    if "doc_date" not in doc_columns:
        op.add_column("documents", sa.Column("doc_date", sa.String(32), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "documents" not in inspector.get_table_names():
        return

    doc_columns = _column_names(inspector, "documents")
    if "doc_date" in doc_columns:
        op.drop_column("documents", "doc_date")
    if "approved_by" in doc_columns:
        op.drop_column("documents", "approved_by")
    if "reviewed_by" in doc_columns:
        op.drop_column("documents", "reviewed_by")
