"""v0.18.0: products and applicability by product

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-07-08 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "k1l2m3n4o5p6"
down_revision: Union[str, Sequence[str], None] = "j0k1l2m3n4o5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(inspector, table: str) -> bool:
    return table in set(inspector.get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not _table_exists(inspector, "products"):
        op.create_table(
            "products",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("slug", sa.String(255), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("project_id", "name", name="uq_products_project_name"),
            sa.UniqueConstraint("project_id", "slug", name="uq_products_project_slug"),
        )

    documents_cols = {col["name"] for col in inspector.get_columns("documents")}
    if "product_id" not in documents_cols:
        op.add_column(
            "documents",
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=True, index=True),
        )

    if _table_exists(inspector, "document_applicability"):
        op.execute(sa.text("DELETE FROM document_applicability"))
        applicability_cols = {col["name"] for col in inspector.get_columns("document_applicability")}
        if "project_id" in applicability_cols:
            op.drop_constraint("uq_document_applicability_doc_project", "document_applicability", type_="unique")
            op.drop_column("document_applicability", "project_id")
        if "product_id" not in applicability_cols:
            op.add_column(
                "document_applicability",
                sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True),
            )
            op.create_unique_constraint(
                "uq_document_applicability_doc_product",
                "document_applicability",
                ["document_id", "product_id"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "document_applicability" in tables:
        applicability_cols = {col["name"] for col in inspector.get_columns("document_applicability")}
        if "product_id" in applicability_cols:
            op.drop_constraint("uq_document_applicability_doc_product", "document_applicability", type_="unique")
            op.drop_column("document_applicability", "product_id")
        if "project_id" not in applicability_cols:
            op.add_column(
                "document_applicability",
                sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
            )
            op.create_unique_constraint(
                "uq_document_applicability_doc_project",
                "document_applicability",
                ["document_id", "project_id"],
            )

    documents_cols = {col["name"] for col in inspector.get_columns("documents")} if "documents" in tables else set()
    if "product_id" in documents_cols:
        op.drop_column("documents", "product_id")

    if "products" in tables:
        op.drop_table("products")
