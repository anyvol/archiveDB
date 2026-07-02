"""v0.10.0: document change log, ИИ, file revisions, status workflow

Revision ID: a1b2c3d4e5f6
Revises: f5a6b7c8d9e0
Create Date: 2026-06-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import ENUM


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DOCUMENT_CHANGE_EVENT_VALUES = (
    "register",
    "file_replace_cosmetic",
    "file_replace_formal",
    "metadata_edit",
    "status_change",
    "correction_request",
    "correction_request_approved",
    "correction_request_rejected",
)
DOCUMENT_CHANGE_EVENT_TYPE_NAME = "documentchangeeventtype"

document_change_event_type = ENUM(*DOCUMENT_CHANGE_EVENT_VALUES, name=DOCUMENT_CHANGE_EVENT_TYPE_NAME)
document_change_event_type_no_create = ENUM(
    *DOCUMENT_CHANGE_EVENT_VALUES,
    name=DOCUMENT_CHANGE_EVENT_TYPE_NAME,
    create_type=False,
)

notification_event_type_new = (
    "correction_request",
    "correction_request_response",
    "formal_change",
)


def _column_names(inspector, table: str) -> set[str]:
    return {col["name"] for col in inspector.get_columns(table)}


def _index_names(inspector, table: str) -> set[str]:
    return {idx["name"] for idx in inspector.get_indexes(table)}


def _enum_labels(bind, type_name: str) -> set[str]:
    rows = bind.execute(
        sa.text(
            """
            SELECT e.enumlabel::text
            FROM pg_enum e
            JOIN pg_type t ON e.enumtypid = t.oid
            WHERE t.typname = :type_name
            """
        ),
        {"type_name": type_name},
    )
    return {row[0] for row in rows}


def _type_exists(bind, type_name: str) -> bool:
    row = bind.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = :type_name"),
        {"type_name": type_name},
    ).first()
    return row is not None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    status_labels = _enum_labels(bind, "documentstatus")
    if "verified" in status_labels and "approved" not in status_labels:
        op.execute("ALTER TYPE documentstatus RENAME VALUE 'verified' TO 'approved'")
    if "correction_requested" not in _enum_labels(bind, "documentstatus"):
        op.execute("ALTER TYPE documentstatus ADD VALUE IF NOT EXISTS 'correction_requested'")

    for val in notification_event_type_new:
        if val not in _enum_labels(bind, "notificationeventtype"):
            op.execute(f"ALTER TYPE notificationeventtype ADD VALUE IF NOT EXISTS '{val}'")

    if not _type_exists(bind, "documentchangeeventtype"):
        document_change_event_type.create(bind, checkfirst=True)

    if "documents" in tables:
        doc_columns = _column_names(inspector, "documents")
        if "correction_request_comment" not in doc_columns:
            op.add_column("documents", sa.Column("correction_request_comment", sa.Text(), nullable=True))

    if "file_revisions" not in tables:
        op.create_table(
            "file_revisions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
            sa.Column("file_name", sa.String(), nullable=False),
            sa.Column("file_path", sa.String(), nullable=False),
            sa.Column("archived_at", sa.DateTime(), nullable=False),
            sa.Column("revision_label", sa.String(), nullable=True),
        )

    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "file_revisions" in tables:
        if "ix_file_revisions_document_id" not in _index_names(inspector, "file_revisions"):
            op.create_index("ix_file_revisions_document_id", "file_revisions", ["document_id"])

    if "change_notifications" not in tables:
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
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "change_notifications" in tables:
        if "ix_change_notifications_document_id" not in _index_names(inspector, "change_notifications"):
            op.create_index("ix_change_notifications_document_id", "change_notifications", ["document_id"])

    if "document_change_events" not in tables:
        op.create_table(
            "document_change_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
            sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("event_type", document_change_event_type_no_create, nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("change_number", sa.String(length=64), nullable=True),
            sa.Column("change_date", sa.DateTime(), nullable=True),
            sa.Column("change_notification_id", sa.Integer(), sa.ForeignKey("change_notifications.id"), nullable=True),
            sa.Column("file_revision_id", sa.Integer(), sa.ForeignKey("file_revisions.id"), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=True),
        )
    inspector = inspect(bind)
    if "document_change_events" in inspector.get_table_names():
        if "ix_document_change_events_document_id" not in _index_names(inspector, "document_change_events"):
            op.create_index("ix_document_change_events_document_id", "document_change_events", ["document_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "document_change_events" in tables:
        indexes = _index_names(inspector, "document_change_events")
        if "ix_document_change_events_document_id" in indexes:
            op.drop_index("ix_document_change_events_document_id", table_name="document_change_events")
        op.drop_table("document_change_events")

    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "change_notifications" in tables:
        indexes = _index_names(inspector, "change_notifications")
        if "ix_change_notifications_document_id" in indexes:
            op.drop_index("ix_change_notifications_document_id", table_name="change_notifications")
        op.drop_table("change_notifications")

    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "file_revisions" in tables:
        indexes = _index_names(inspector, "file_revisions")
        if "ix_file_revisions_document_id" in indexes:
            op.drop_index("ix_file_revisions_document_id", table_name="file_revisions")
        op.drop_table("file_revisions")

    if "documents" in tables:
        doc_columns = _column_names(inspector, "documents")
        if "correction_request_comment" in doc_columns:
            op.drop_column("documents", "correction_request_comment")

    if _type_exists(bind, "documentchangeeventtype"):
        document_change_event_type.drop(bind, checkfirst=True)

    status_labels = _enum_labels(bind, "documentstatus")
    if "approved" in status_labels and "verified" not in status_labels:
        op.execute("ALTER TYPE documentstatus RENAME VALUE 'approved' TO 'verified'")
