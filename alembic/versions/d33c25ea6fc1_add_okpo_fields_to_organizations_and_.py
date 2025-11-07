"""add okpo fields to organizations and remove department

Revision ID: d33c25ea6fc1
Revises: bdff88f0ac97
Create Date: 2025-11-07 14:06:18.807478

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd33c25ea6fc1'
down_revision: Union[str, Sequence[str], None] = 'bdff88f0ac97'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Добавление новых столбцов
    op.add_column('organizations', sa.Column('code_okpo', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('organizations', sa.Column('num_code', sa.Integer(), nullable=True))
    op.add_column('organizations', sa.Column('num_code_okpo', sa.Integer(), nullable=True))
    
    # Удаление department
    op.drop_column('organizations', 'department')

def downgrade():
    op.add_column('organizations', sa.Column('department', sa.VARCHAR(length=255), nullable=True))
    op.drop_column('organizations', 'num_code_okpo')
    op.drop_column('organizations', 'num_code')
    op.drop_column('organizations', 'code_okpo')
