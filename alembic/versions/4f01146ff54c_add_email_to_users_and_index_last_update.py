"""add_email_to_users_and_index_last_update

Revision ID: 4f01146ff54c
Revises: f5cce59638b6
Create Date: 2025-11-10 23:48:17.141337

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f01146ff54c'
down_revision: Union[str, Sequence[str], None] = 'f5cce59638b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('email', sa.String(length=100), nullable=True))
    op.create_index('ix_documents_last_update', 'documents', ['last_update'])
    pass


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_documents_last_update', table_name='documents')
    op.drop_column('users', 'email')  # Rollback безопасен
    pass
