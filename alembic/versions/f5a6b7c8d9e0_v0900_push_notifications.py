"""v0.9.0: browser push notification preferences and subscriptions

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-06-29 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, Sequence[str], None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(inspector, table: str) -> set[str]:
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "users" in tables:
        user_columns = _column_names(inspector, "users")
        if "push_subscription" not in user_columns:
            op.add_column("users", sa.Column("push_subscription", sa.JSON(), nullable=True))
        if "push_preferences" not in user_columns:
            op.add_column("users", sa.Column("push_preferences", sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "users" in tables:
        user_columns = _column_names(inspector, "users")
        if "push_preferences" in user_columns:
            op.drop_column("users", "push_preferences")
        if "push_subscription" in user_columns:
            op.drop_column("users", "push_subscription")
