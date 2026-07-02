"""v0.12.0: document format, project description, project files and images

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(inspector, table: str) -> set[str]:
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "documents" in tables:
        doc_columns = _column_names(inspector, "documents")
        if "document_format" not in doc_columns:
            op.add_column("documents", sa.Column("document_format", sa.String(32), nullable=True))

    if "projects" in tables:
        project_columns = _column_names(inspector, "projects")
        if "description" not in project_columns:
            op.add_column("projects", sa.Column("description", sa.Text(), nullable=True))
        if "created_at" not in project_columns:
            op.add_column("projects", sa.Column("created_at", sa.DateTime(), nullable=True))

    if "project_files" not in tables:
        op.create_table(
            "project_files",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False, index=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("file_name", sa.String(), nullable=False),
            sa.Column("file_path", sa.String(), nullable=False),
            sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    if "project_images" not in tables:
        op.create_table(
            "project_images",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False, index=True),
            sa.Column("file_name", sa.String(), nullable=False),
            sa.Column("file_path", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "project_images" in tables:
        op.drop_table("project_images")
    if "project_files" in tables:
        op.drop_table("project_files")

    if "projects" in tables:
        project_columns = _column_names(inspector, "projects")
        if "created_at" in project_columns:
            op.drop_column("projects", "created_at")
        if "description" in project_columns:
            op.drop_column("projects", "description")

    if "documents" in tables:
        doc_columns = _column_names(inspector, "documents")
        if "document_format" in doc_columns:
            op.drop_column("documents", "document_format")
