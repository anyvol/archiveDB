"""add review_comment and registration_notified_at to documents

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-06-26 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(inspector, table: str) -> set[str]:
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "documents" not in inspector.get_table_names():
        return
    columns = _column_names(inspector, "documents")
    if "review_comment" not in columns:
        op.add_column("documents", sa.Column("review_comment", sa.Text(), nullable=True))
    if "registration_notified_at" not in columns:
        op.add_column("documents", sa.Column("registration_notified_at", sa.DateTime(), nullable=True))

    op.execute(
        sa.text(
            """
            DO $$ BEGIN
                ALTER TYPE notificationeventtype ADD VALUE 'document_register';
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "documents" not in inspector.get_table_names():
        return
    columns = _column_names(inspector, "documents")
    if "registration_notified_at" in columns:
        op.drop_column("documents", "registration_notified_at")
    if "review_comment" in columns:
        op.drop_column("documents", "review_comment")
