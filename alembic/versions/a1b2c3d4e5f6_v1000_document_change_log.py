"""v0.10.0: document change log, ИИ, file revisions, status workflow

Revision ID: a1b2c3d4e5f6
Revises: f5a6b7c8d9e0
Create Date: 2026-06-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

document_change_event_type = sa.Enum(
    "register",
    "file_replace_cosmetic",
    "file_replace_formal",
    "metadata_edit",
    "status_change",
    "correction_request",
    "correction_request_approved",
    "correction_request_rejected",
    name="documentchangeeventtype",
)

notification_event_type_new = (
    "correction_request",
    "correction_request_response",
    "formal_change",
)


def _column_names(inspector, table: str) -> set[str]:
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    # Rename verified -> approved and add correction_requested to documentstatus enum
    op.execute("ALTER TYPE documentstatus RENAME VALUE 'verified' TO 'approved'")
    op.execute("ALTER TYPE documentstatus ADD VALUE IF NOT EXISTS 'correction_requested'")

    # Extend notification event type enum
    for val in notification_event_type_new:
        op.execute(f"ALTER TYPE notificationeventtype ADD VALUE IF NOT EXISTS '{val}'")

    document_change_event_type.create(bind, checkfirst=True)

    doc_columns = _column_names(inspector, "documents") if "documents" in inspector.get_table_names() else set()
    if "correction_request_comment" not in doc_columns:
        op.add_column("documents", sa.Column("correction_request_comment", sa.Text(), nullable=True))

    op.create_table(
        "file_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("file_name", sa.String(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("archived_at", sa.DateTime(), nullable=False),
        sa.Column("revision_label", sa.String(), nullable=True),
    )
    op.create_index("ix_file_revisions_document_id", "file_revisions", ["document_id"])

    op.create_table(
        "change_notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("number", sa.String(length=64), nullable=False),
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.Column("file_name", sa.String(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("developer_signed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("reviewer_signed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("approver_signed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
    )
    op.create_index("ix_change_notifications_document_id", "change_notifications", ["document_id"])

    op.create_table(
        "document_change_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("event_type", document_change_event_type, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("change_number", sa.String(length=64), nullable=True),
        sa.Column("change_date", sa.DateTime(), nullable=True),
        sa.Column("change_notification_id", sa.Integer(), sa.ForeignKey("change_notifications.id"), nullable=True),
        sa.Column("file_revision_id", sa.Integer(), sa.ForeignKey("file_revisions.id"), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
    )
    op.create_index("ix_document_change_events_document_id", "document_change_events", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_document_change_events_document_id", table_name="document_change_events")
    op.drop_table("document_change_events")
    op.drop_index("ix_change_notifications_document_id", table_name="change_notifications")
    op.drop_table("change_notifications")
    op.drop_index("ix_file_revisions_document_id", table_name="file_revisions")
    op.drop_table("file_revisions")

    bind = op.get_bind()
    inspector = inspect(bind)
    doc_columns = _column_names(inspector, "documents") if "documents" in inspector.get_table_names() else set()
    if "correction_request_comment" in doc_columns:
        op.drop_column("documents", "correction_request_comment")

    document_change_event_type.drop(bind, checkfirst=True)

    op.execute("ALTER TYPE documentstatus RENAME VALUE 'approved' TO 'verified'")
