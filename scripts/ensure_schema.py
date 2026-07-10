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
            if "doc_date" in doc_columns and "developer_signed_date" not in doc_columns:
                conn.execute(
                    text("ALTER TABLE documents RENAME COLUMN doc_date TO developer_signed_date")
                )
                applied.append("documents.doc_date -> developer_signed_date")
            elif "developer_signed_date" not in doc_columns:
                conn.execute(
                    text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS developer_signed_date VARCHAR(32)")
                )
                applied.append("documents.developer_signed_date")
            if "reviewer_signed_date" not in doc_columns:
                conn.execute(
                    text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS reviewer_signed_date VARCHAR(32)")
                )
                applied.append("documents.reviewer_signed_date")
            if "approver_signed_date" not in doc_columns:
                conn.execute(
                    text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS approver_signed_date VARCHAR(32)")
                )
                applied.append("documents.approver_signed_date")

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
        if "developer_signed_date" not in _column_names(inspector, "documents"):
            missing.append("documents.developer_signed_date")
        if "reviewer_signed_date" not in _column_names(inspector, "documents"):
            missing.append("documents.reviewer_signed_date")
        if "approver_signed_date" not in _column_names(inspector, "documents"):
            missing.append("documents.approver_signed_date")
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


def _apply_ocr_schema(engine) -> list[str]:
    """Create OCR tables if Alembic version advanced without DDL (phase 1A repair)."""
    applied: list[str] = []
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        if "ocr_batches" not in tables:
            conn.execute(
                text(
                    """
                    CREATE TABLE ocr_batches (
                        id SERIAL PRIMARY KEY,
                        created_by_user_id INTEGER NOT NULL REFERENCES users(id),
                        created_at TIMESTAMP NOT NULL DEFAULT now(),
                        status VARCHAR(32) NOT NULL DEFAULT 'open'
                    )
                    """
                )
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ocr_batches_created_by_user_id ON ocr_batches (created_by_user_id)"))
            applied.append("ocr_batches")

        inspector = inspect(engine)
        tables = set(inspector.get_table_names())

        if "ocr_jobs" not in tables:
            conn.execute(
                text(
                    """
                    CREATE TABLE ocr_jobs (
                        id SERIAL PRIMARY KEY,
                        batch_id INTEGER NOT NULL REFERENCES ocr_batches(id),
                        original_filename VARCHAR(512) NOT NULL,
                        stored_path VARCHAR(1024) NOT NULL,
                        mime VARCHAR(128),
                        page_count INTEGER,
                        status VARCHAR(32) NOT NULL DEFAULT 'queued',
                        error_message TEXT,
                        pipeline_version VARCHAR(64),
                        started_at TIMESTAMP,
                        finished_at TIMESTAMP,
                        document_id INTEGER REFERENCES documents(id),
                        created_at TIMESTAMP NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ocr_jobs_batch_id ON ocr_jobs (batch_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ocr_jobs_document_id ON ocr_jobs (document_id)"))
            applied.append("ocr_jobs")

        inspector = inspect(engine)
        tables = set(inspector.get_table_names())

        if "ocr_extractions" not in tables:
            conn.execute(
                text(
                    """
                    CREATE TABLE ocr_extractions (
                        id SERIAL PRIMARY KEY,
                        job_id INTEGER NOT NULL REFERENCES ocr_jobs(id),
                        created_at TIMESTAMP NOT NULL DEFAULT now(),
                        source VARCHAR(32) NOT NULL DEFAULT 'auto',
                        fields JSON NOT NULL DEFAULT '{}'::json,
                        geometry JSON NOT NULL DEFAULT '{}'::json,
                        stamp_crop_path VARCHAR(1024),
                        page_preview_path VARCHAR(1024),
                        person_suggestions JSON
                    )
                    """
                )
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ocr_extractions_job_id ON ocr_extractions (job_id)"))
            applied.append("ocr_extractions")

    return applied


def main() -> int:
    engine = create_engine(_resolve_database_url())
    current = _alembic_version(engine)
    print(f"Alembic version in DB: {current or '(none)'}")

    applied = _apply_v1200_schema(engine)
    if applied:
        print("Schema repair applied:", ", ".join(applied))
    else:
        print("Schema repair: all 0.12.0 objects already present.")

    ocr_applied = _apply_ocr_schema(engine)
    if ocr_applied:
        print("OCR schema repair applied:", ", ".join(ocr_applied))
    else:
        print("OCR schema repair: ocr_* tables already present.")

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
