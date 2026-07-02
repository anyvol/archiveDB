"""v0.12.0: rename doc_date to developer_signed_date, add reviewer/approver signed dates

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-02 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
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
    if "doc_date" in doc_columns and "developer_signed_date" not in doc_columns:
        op.alter_column("documents", "doc_date", new_column_name="developer_signed_date")
        doc_columns = _column_names(inspect(bind), "documents")
    elif "developer_signed_date" not in doc_columns:
        op.add_column("documents", sa.Column("developer_signed_date", sa.String(32), nullable=True))

    doc_columns = _column_names(inspect(bind), "documents")
    if "reviewer_signed_date" not in doc_columns:
        op.add_column("documents", sa.Column("reviewer_signed_date", sa.String(32), nullable=True))
    if "approver_signed_date" not in doc_columns:
        op.add_column("documents", sa.Column("approver_signed_date", sa.String(32), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "documents" not in inspector.get_table_names():
        return

    doc_columns = _column_names(inspector, "documents")
    if "approver_signed_date" in doc_columns:
        op.drop_column("documents", "approver_signed_date")
    if "reviewer_signed_date" in doc_columns:
        op.drop_column("documents", "reviewer_signed_date")
    if "developer_signed_date" in doc_columns:
        if "doc_date" not in doc_columns:
            op.alter_column("documents", "developer_signed_date", new_column_name="doc_date")
        else:
            op.drop_column("documents", "developer_signed_date")
