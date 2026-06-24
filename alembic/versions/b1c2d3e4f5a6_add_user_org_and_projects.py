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
from sqlalchemy import inspect


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


def _column_names(inspector, table: str) -> set[str]:
    return {col["name"] for col in inspector.get_columns(table)}


def _index_names(inspector, table: str) -> set[str]:
    return {idx["name"] for idx in inspector.get_indexes(table)}


def _ensure_legacy_project(conn) -> int:
    legacy_id = conn.execute(
        sa.text("SELECT id FROM projects WHERE slug = '_legacy'")
    ).scalar()
    if legacy_id is not None:
        return legacy_id

    legacy_id = conn.execute(
        sa.text(
            "INSERT INTO projects (name, slug) VALUES ('Без проекта', '_legacy') RETURNING id"
        )
    ).scalar()
    return legacy_id


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    user_columns = _column_names(inspector, "users") if "users" in tables else set()
    if "preferred_org_code" not in user_columns:
        op.add_column("users", sa.Column("preferred_org_code", sa.String(length=8), nullable=True))
    if "preferred_org_okpo" not in user_columns:
        op.add_column(
            "users",
            sa.Column(
                "preferred_org_okpo",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )

    if "projects" not in tables:
        op.create_table(
            "projects",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("slug", sa.String(length=255), nullable=False),
        )
        inspector = inspect(bind)

    project_indexes = _index_names(inspector, "projects")
    if "ix_projects_name" not in project_indexes:
        op.create_index("ix_projects_name", "projects", ["name"], unique=True)
    if "ix_projects_slug" not in project_indexes:
        op.create_index("ix_projects_slug", "projects", ["slug"], unique=True)

    legacy_project_id = _ensure_legacy_project(bind)

    doc_columns = _column_names(inspector, "documents") if "documents" in tables else set()
    if "project_id" not in doc_columns:
        op.add_column("documents", sa.Column("project_id", sa.Integer(), nullable=True))

    bind.execute(
        sa.text(
            "UPDATE documents SET project_id = :legacy_id WHERE project_id IS NULL"
        ),
        {"legacy_id": legacy_project_id},
    )

    # NOT NULL + FK only when all rows have project_id
    null_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM documents WHERE project_id IS NULL")
    ).scalar()
    if null_count == 0:
        project_col = next(c for c in inspect(bind).get_columns("documents") if c["name"] == "project_id")
        if project_col.get("nullable", True):
            op.alter_column("documents", "project_id", nullable=False)

    fks = inspector.get_foreign_keys("documents")
    has_project_fk = any("project_id" in fk.get("constrained_columns", []) for fk in fks)
    if not has_project_fk:
        op.create_foreign_key(
            "fk_documents_project_id",
            "documents",
            "projects",
            ["project_id"],
            ["id"],
        )

    upload_dir = os.getenv("UPLOAD_DIR", "uploaded_files")
    legacy_dir = os.path.join(upload_dir, "_legacy")
    _migrate_files_to_legacy(upload_dir, legacy_dir)

    rows = bind.execute(
        sa.text("SELECT id, file_path FROM documents WHERE file_path IS NOT NULL")
    ).fetchall()
    for doc_id, file_path in rows:
        if not file_path:
            continue
        basename = os.path.basename(file_path)
        new_path = os.path.join(legacy_dir, basename)
        if os.path.exists(new_path) or file_path == new_path:
            bind.execute(
                sa.text("UPDATE documents SET file_path = :new_path WHERE id = :doc_id"),
                {"new_path": new_path, "doc_id": doc_id},
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "documents" in tables:
        fk_names = {fk["name"] for fk in inspector.get_foreign_keys("documents")}
        if "fk_documents_project_id" in fk_names:
            op.drop_constraint("fk_documents_project_id", "documents", type_="foreignkey")
        doc_columns = _column_names(inspector, "documents")
        if "project_id" in doc_columns:
            op.drop_column("documents", "project_id")

    if "projects" in tables:
        project_indexes = _index_names(inspector, "projects")
        if "ix_projects_slug" in project_indexes:
            op.drop_index("ix_projects_slug", table_name="projects")
        if "ix_projects_name" in project_indexes:
            op.drop_index("ix_projects_name", table_name="projects")
        op.drop_table("projects")

    if "users" in tables:
        user_columns = _column_names(inspector, "users")
        if "preferred_org_okpo" in user_columns:
            op.drop_column("users", "preferred_org_okpo")
        if "preferred_org_code" in user_columns:
            op.drop_column("users", "preferred_org_code")
