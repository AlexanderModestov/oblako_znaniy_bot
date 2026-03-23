"""add max_user_id to users

Revision ID: d5486c85a6e8
Revises: 004
Create Date: 2026-03-23 00:54:01.639277

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5486c85a6e8'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('max_user_id', sa.BigInteger(), nullable=True))
    op.create_unique_constraint('uq_users_max_user_id', 'users', ['max_user_id'])
    op.alter_column('users', 'telegram_id', nullable=True)


def downgrade() -> None:
    op.alter_column('users', 'telegram_id', nullable=False)
    op.drop_constraint('uq_users_max_user_id', 'users', type_='unique')
    op.drop_column('users', 'max_user_id')
