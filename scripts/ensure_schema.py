"""Apply missing 0.12.0 schema objects when Alembic reports head but DDL was not applied."""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text

load_dotenv()

V1200_REVISION = "c3d4e5f6a7b8"


def _sync_database_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def _resolve_database_url() -> str:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")

    alembic_env = os.getenv("ALEMBIC_DATABASE_URL", "").strip()
    sync_from_app = _sync_database_url(database_url)
    if alembic_env and "@db:" in database_url and "@localhost" in alembic_env:
        return sync_from_app
    if alembic_env:
        return alembic_env
    return sync_from_app


def _column_names(inspector, table: str) -> set[str]:
    return {col["name"] for col in inspector.get_columns(table)}


def _apply_v1200_schema(engine) -> list[str]:
    applied: list[str] = []
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        if "documents" in tables:
            doc_columns = _column_names(inspector, "documents")
            if "document_format" not in doc_columns:
                conn.execute(
                    text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS document_format VARCHAR(32)")
                )
                applied.append("documents.document_format")
            if "reviewed_by" not in doc_columns:
                conn.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS reviewed_by VARCHAR"))
                applied.append("documents.reviewed_by")
            if "approved_by" not in doc_columns:
                conn.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS approved_by VARCHAR"))
                applied.append("documents.approved_by")
            if "doc_date" not in doc_columns:
                conn.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS doc_date VARCHAR(32)"))
                applied.append("documents.doc_date")

        if "projects" in tables:
            project_columns = _column_names(inspector, "projects")
            if "description" not in project_columns:
                conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS description TEXT"))
                applied.append("projects.description")
            if "created_at" not in project_columns:
                conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS created_at TIMESTAMP"))
                applied.append("projects.created_at")

        inspector = inspect(engine)
        tables = set(inspector.get_table_names())

        if "project_files" not in tables:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS project_files (
                        id SERIAL PRIMARY KEY,
                        project_id INTEGER NOT NULL REFERENCES projects(id),
                        title VARCHAR(255) NOT NULL,
                        file_name VARCHAR NOT NULL,
                        file_path VARCHAR NOT NULL,
                        uploaded_by INTEGER NOT NULL REFERENCES users(id),
                        created_at TIMESTAMP NOT NULL
                    )
                    """
                )
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_project_files_project_id ON project_files (project_id)"))
            applied.append("project_files")

        if "project_images" not in tables:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS project_images (
                        id SERIAL PRIMARY KEY,
                        project_id INTEGER NOT NULL REFERENCES projects(id),
                        file_name VARCHAR NOT NULL,
                        file_path VARCHAR NOT NULL,
                        created_at TIMESTAMP NOT NULL
                    )
                    """
                )
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_project_images_project_id ON project_images (project_id)"))
            applied.append("project_images")

    return applied


def _alembic_version(engine) -> str | None:
    inspector = inspect(engine)
    if "alembic_version" not in inspector.get_table_names():
        return None
    with engine.connect() as conn:
        row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).first()
    return row[0] if row else None


def _verify_schema(engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    missing: list[str] = []

    if "documents" in tables:
        if "document_format" not in _column_names(inspector, "documents"):
            missing.append("documents.document_format")
        if "reviewed_by" not in _column_names(inspector, "documents"):
            missing.append("documents.reviewed_by")
        if "approved_by" not in _column_names(inspector, "documents"):
            missing.append("documents.approved_by")
        if "doc_date" not in _column_names(inspector, "documents"):
            missing.append("documents.doc_date")
    if "projects" in tables:
        project_columns = _column_names(inspector, "projects")
        if "description" not in project_columns:
            missing.append("projects.description")
        if "created_at" not in project_columns:
            missing.append("projects.created_at")
    if "project_files" not in tables:
        missing.append("project_files")
    if "project_images" not in tables:
        missing.append("project_images")

    if missing:
        raise RuntimeError(f"Schema verification failed, missing: {', '.join(missing)}")


def main() -> int:
    engine = create_engine(_resolve_database_url())
    current = _alembic_version(engine)
    print(f"Alembic version in DB: {current or '(none)'}")

    applied = _apply_v1200_schema(engine)
    if applied:
        print("Schema repair applied:", ", ".join(applied))
    else:
        print("Schema repair: all 0.12.0 objects already present.")

    _verify_schema(engine)
    print("Schema verification OK.")

    current_after = _alembic_version(engine)
    if current_after and current_after != V1200_REVISION:
        print(
            f"Note: alembic_version is {current_after}, expected {V1200_REVISION} after full upgrade. "
            "Run: docker compose exec api alembic upgrade head"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Schema ensure failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
