"""v0.26.0: electronic specification model, entries, auto_draft status

Revision ID: s9t0u1v2w3x4
Revises: r8s9t0u1v2w3
Create Date: 2026-07-13 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "s9t0u1v2w3x4"
down_revision: Union[str, Sequence[str], None] = "r8s9t0u1v2w3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(inspector, table: str) -> set[str]:
    return {col["name"] for col in inspector.get_columns(table)}


def _table_exists(inspector, table: str) -> bool:
    return table in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    # Extend documentstatus enum (PostgreSQL)
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE documentstatus ADD VALUE IF NOT EXISTS 'auto_draft'")

    if _table_exists(inspector, "documents"):
        columns = _column_names(inspector, "documents")
        if "is_specification" not in columns:
            op.add_column(
                "documents",
                sa.Column("is_specification", sa.Boolean(), nullable=False, server_default=sa.false()),
            )
        if "contains_embedded_specification" not in columns:
            op.add_column(
                "documents",
                sa.Column(
                    "contains_embedded_specification",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                ),
            )
        if "assembly_document_id" not in columns:
            op.add_column(
                "documents",
                sa.Column("assembly_document_id", sa.Integer(), nullable=True),
            )
            op.create_foreign_key(
                "fk_documents_assembly_document_id",
                "documents",
                "documents",
                ["assembly_document_id"],
                ["id"],
                ondelete="SET NULL",
            )
            op.create_index("ix_documents_assembly_document_id", "documents", ["assembly_document_id"])
        if "specification_document_id" not in columns:
            op.add_column(
                "documents",
                sa.Column("specification_document_id", sa.Integer(), nullable=True),
            )
            op.create_foreign_key(
                "fk_documents_specification_document_id",
                "documents",
                "documents",
                ["specification_document_id"],
                ["id"],
                ondelete="SET NULL",
            )
            op.create_index("ix_documents_specification_document_id", "documents", ["specification_document_id"])

    if not _table_exists(inspector, "specification_entries"):
        op.create_table(
            "specification_entries",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("host_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
            sa.Column("section", sa.String(64), nullable=False, server_default=""),
            sa.Column("position", sa.String(16), nullable=True),
            sa.Column("row_format", sa.String(16), nullable=True),
            sa.Column("zone", sa.String(16), nullable=True),
            sa.Column("row_designation", sa.String(128), nullable=True),
            sa.Column("row_name", sa.String(512), nullable=True),
            sa.Column("quantity", sa.String(32), nullable=True),
            sa.Column("note", sa.String(512), nullable=True),
            sa.Column("linked_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
            sa.Column("match_confidence", sa.String(16), nullable=True),
            sa.Column("source", sa.String(16), nullable=False, server_default="ocr"),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_specification_entries_host_document_id", "specification_entries", ["host_document_id"])
        op.create_index("ix_specification_entries_linked_document_id", "specification_entries", ["linked_document_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if _table_exists(inspector, "specification_entries"):
        op.drop_table("specification_entries")
    if _table_exists(inspector, "documents"):
        columns = _column_names(inspector, "documents")
        if "specification_document_id" in columns:
            op.drop_constraint("fk_documents_specification_document_id", "documents", type_="foreignkey")
            op.drop_index("ix_documents_specification_document_id", table_name="documents")
            op.drop_column("documents", "specification_document_id")
        if "assembly_document_id" in columns:
            op.drop_constraint("fk_documents_assembly_document_id", "documents", type_="foreignkey")
            op.drop_index("ix_documents_assembly_document_id", table_name="documents")
            op.drop_column("documents", "assembly_document_id")
        if "contains_embedded_specification" in columns:
            op.drop_column("documents", "contains_embedded_specification")
        if "is_specification" in columns:
            op.drop_column("documents", "is_specification")
