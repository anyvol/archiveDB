"""v0.17.0: document applicability and links

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-07-07 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "j0k1l2m3n4o5"
down_revision: Union[str, Sequence[str], None] = "i9j0k1l2m3n4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(inspector, table: str) -> bool:
    return table in set(inspector.get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not _table_exists(inspector, "document_applicability"):
        op.create_table(
            "document_applicability",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("file_path", sa.String(), nullable=False),
            sa.Column("file_name", sa.String(), nullable=False),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("document_id", "project_id", name="uq_document_applicability_doc_project"),
        )

    if not _table_exists(inspector, "document_links"):
        op.create_table(
            "document_links",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("target_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("source_document_id", "target_document_id", name="uq_document_links_source_target"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "document_links" in tables:
        op.drop_table("document_links")
    if "document_applicability" in tables:
        op.drop_table("document_applicability")
