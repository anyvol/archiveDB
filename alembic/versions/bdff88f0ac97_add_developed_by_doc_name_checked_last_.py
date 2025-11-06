"""add_developed_by_doc_name_checked_last_update_to_documents

Revision ID: bdff88f0ac97
Revises: 73670f11a96e
Create Date: 2025-11-06 23:31:12.707806

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from datetime import datetime


# revision identifiers, used by Alembic.
revision: str = 'bdff88f0ac97'
down_revision: Union[str, Sequence[str], None] = '73670f11a96e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Добавление колонок в таблицу documents
    op.add_column('documents', sa.Column('developed_by', sa.String(), nullable=True))
    op.add_column('documents', sa.Column('doc_name', sa.String(), nullable=True))
    op.add_column('documents', sa.Column('checked', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('documents', sa.Column('last_update', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()))
    
    # Обновление существующих записей (last_update = created_at)
    op.execute("UPDATE documents SET last_update = created_at WHERE last_update IS NULL")


def downgrade():
    # Удаление колонок (для rollback)
    op.drop_column('documents', 'last_update')
    op.drop_column('documents', 'checked')
    op.drop_column('documents', 'doc_name')
    op.drop_column('documents', 'developed_by')
