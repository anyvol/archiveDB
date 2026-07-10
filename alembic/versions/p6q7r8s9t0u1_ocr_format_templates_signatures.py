"""OCR format-bound ROI templates and signature presence flags.

Revision ID: p6q7r8s9t0u1
Revises: o5p6q7r8s9t0
Create Date: 2026-07-10 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "p6q7r8s9t0u1"
down_revision: Union[str, Sequence[str], None] = "o5p6q7r8s9t0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(inspector, table: str) -> bool:
    return table in set(inspector.get_table_names())


def _column_names(inspector, table: str) -> set[str]:
    if not _table_exists(inspector, table):
        return set()
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not _table_exists(inspector, "ocr_format_templates"):
        op.create_table(
            "ocr_format_templates",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("document_format", sa.String(length=32), nullable=False, unique=True),
            sa.Column("labels", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        )

    doc_cols = _column_names(inspector, "documents")
    if "documents" in set(inspector.get_table_names()):
        if "has_developer_signature" not in doc_cols:
            op.add_column(
                "documents",
                sa.Column("has_developer_signature", sa.Boolean(), nullable=True),
            )
        if "has_reviewer_signature" not in doc_cols:
            op.add_column(
                "documents",
                sa.Column("has_reviewer_signature", sa.Boolean(), nullable=True),
            )
        if "has_approver_signature" not in doc_cols:
            op.add_column(
                "documents",
                sa.Column("has_approver_signature", sa.Boolean(), nullable=True),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    doc_cols = _column_names(inspector, "documents")
    if "has_approver_signature" in doc_cols:
        op.drop_column("documents", "has_approver_signature")
    if "has_reviewer_signature" in doc_cols:
        op.drop_column("documents", "has_reviewer_signature")
    if "has_developer_signature" in doc_cols:
        op.drop_column("documents", "has_developer_signature")
    if _table_exists(inspector, "ocr_format_templates"):
        op.drop_table("ocr_format_templates")
