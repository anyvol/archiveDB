"""v0.11.0: document signature metadata fields

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-30 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("reviewed_by", sa.String(), nullable=True))
    op.add_column("documents", sa.Column("approved_by", sa.String(), nullable=True))
    op.add_column("documents", sa.Column("developed_date", sa.Date(), nullable=True))
    op.add_column("documents", sa.Column("reviewed_date", sa.Date(), nullable=True))
    op.add_column("documents", sa.Column("approved_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "approved_date")
    op.drop_column("documents", "reviewed_date")
    op.drop_column("documents", "developed_date")
    op.drop_column("documents", "approved_by")
    op.drop_column("documents", "reviewed_by")
