"""Drop municipality_name, add inn to schools; make users.school_id nullable.

Revision ID: 008
Revises: 007
Create Date: 2026-03-25
"""

import sqlalchemy as sa
from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("schools", "municipality_name")
    op.add_column("schools", sa.Column("inn", sa.String(length=20), nullable=True))
    op.alter_column("users", "school_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.alter_column("users", "school_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("schools", "inn")
    op.add_column("schools", sa.Column("municipality_name", sa.String(length=255), nullable=True))
