"""Add doc_kind_code to DesignDocument

Revision ID: f5cce59638b6
Revises: d33c25ea6fc1
Create Date: 2025-11-10 20:59:10.606578

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f5cce59638b6'
down_revision: Union[str, Sequence[str], None] = 'd33c25ea6fc1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():

    op.add_column('design_documents', sa.Column('doc_kind_code', sa.String(length=3), nullable=True))


def downgrade():

    op.drop_column('design_documents', 'doc_kind_code')

