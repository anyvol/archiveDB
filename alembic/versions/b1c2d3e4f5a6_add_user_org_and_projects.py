"""add user preferred org and projects

Revision ID: b1c2d3e4f5a6
Revises: 8a7eb69bb820
Create Date: 2026-06-24 12:00:00.000000

"""
import os
import shutil
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "8a7eb69bb820"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _migrate_files_to_legacy(upload_dir: str, legacy_dir: str) -> None:
    if not os.path.isdir(upload_dir):
        return
    os.makedirs(legacy_dir, exist_ok=True)
    for entry in os.listdir(upload_dir):
        src = os.path.join(upload_dir, entry)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(legacy_dir, entry)
        if not os.path.exists(dst):
            shutil.move(src, dst)


def upgrade() -> None:
    op.add_column("users", sa.Column("preferred_org_code", sa.String(length=8), nullable=True))
    op.add_column(
        "users",
        sa.Column("preferred_org_okpo", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
    )
    op.create_index("ix_projects_name", "projects", ["name"], unique=True)
    op.create_index("ix_projects_slug", "projects", ["slug"], unique=True)

    projects = sa.table(
        "projects",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("slug", sa.String),
    )
    op.bulk_insert(projects, [{"name": "Без проекта", "slug": "_legacy"}])

    op.add_column("documents", sa.Column("project_id", sa.Integer(), nullable=True))
    op.execute(sa.text("UPDATE documents SET project_id = (SELECT id FROM projects WHERE slug = '_legacy')"))
    op.alter_column("documents", "project_id", nullable=False)
    op.create_foreign_key("fk_documents_project_id", "documents", "projects", ["project_id"], ["id"])

    upload_dir = os.getenv("UPLOAD_DIR", "uploaded_files")
    legacy_dir = os.path.join(upload_dir, "_legacy")
    _migrate_files_to_legacy(upload_dir, legacy_dir)

    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, file_path FROM documents WHERE file_path IS NOT NULL")
    ).fetchall()
    for doc_id, file_path in rows:
        if not file_path:
            continue
        basename = os.path.basename(file_path)
        new_path = os.path.join(legacy_dir, basename)
        if os.path.exists(new_path) or file_path == new_path:
            conn.execute(
                sa.text("UPDATE documents SET file_path = :new_path WHERE id = :doc_id"),
                {"new_path": new_path, "doc_id": doc_id},
            )


def downgrade() -> None:
    op.drop_constraint("fk_documents_project_id", "documents", type_="foreignkey")
    op.drop_column("documents", "project_id")
    op.drop_index("ix_projects_slug", table_name="projects")
    op.drop_index("ix_projects_name", table_name="projects")
    op.drop_table("projects")
    op.drop_column("users", "preferred_org_okpo")
    op.drop_column("users", "preferred_org_code")
