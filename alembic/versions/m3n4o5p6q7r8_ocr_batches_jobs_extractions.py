"""OCR tables for stamp recognition pipeline (phase 1A).

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-07-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "m3n4o5p6q7r8"
down_revision: Union[str, Sequence[str], None] = "l2m3n4o5p6q7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(inspector, table: str) -> bool:
    return table in set(inspector.get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    ocr_batch_status = sa.Enum(
        "open",
        "processing",
        "completed",
        "failed",
        name="ocrbatchstatus",
    )
    ocr_job_status = sa.Enum(
        "queued",
        "processing",
        "needs_review",
        "needs_annotation",
        "ready",
        "committed",
        "failed",
        "discarded",
        name="ocrjobstatus",
    )

    if not _table_exists(inspector, "ocr_batches"):
        ocr_batch_status.create(bind, checkfirst=True)
        op.create_table(
            "ocr_batches",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.Column("status", ocr_batch_status, nullable=False, server_default="open"),
        )

    if not _table_exists(inspector, "ocr_jobs"):
        ocr_job_status.create(bind, checkfirst=True)
        op.create_table(
            "ocr_jobs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("batch_id", sa.Integer(), sa.ForeignKey("ocr_batches.id"), nullable=False, index=True),
            sa.Column("original_filename", sa.String(512), nullable=False),
            sa.Column("stored_path", sa.String(1024), nullable=False),
            sa.Column("mime", sa.String(128), nullable=True),
            sa.Column("page_count", sa.Integer(), nullable=True),
            sa.Column("status", ocr_job_status, nullable=False, server_default="queued"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("pipeline_version", sa.String(64), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=True, index=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        )

    if not _table_exists(inspector, "ocr_extractions"):
        op.create_table(
            "ocr_extractions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("job_id", sa.Integer(), sa.ForeignKey("ocr_jobs.id"), nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.Column("source", sa.String(32), nullable=False, server_default="auto"),
            sa.Column("fields", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("geometry", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("stamp_crop_path", sa.String(1024), nullable=True),
            sa.Column("page_preview_path", sa.String(1024), nullable=True),
            sa.Column("person_suggestions", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if _table_exists(inspector, "ocr_extractions"):
        op.drop_table("ocr_extractions")
    if _table_exists(inspector, "ocr_jobs"):
        op.drop_table("ocr_jobs")
    if _table_exists(inspector, "ocr_batches"):
        op.drop_table("ocr_batches")

    sa.Enum(name="ocrjobstatus").drop(bind, checkfirst=True)
    sa.Enum(name="ocrbatchstatus").drop(bind, checkfirst=True)
