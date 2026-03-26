"""Drop code column from subjects table.

Revision ID: 009
Revises: 008
Create Date: 2026-03-26
"""

import sqlalchemy as sa
from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("subjects", "code")


def downgrade() -> None:
    op.add_column("subjects", sa.Column("code", sa.String(length=50), nullable=True))
