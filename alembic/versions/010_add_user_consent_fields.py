"""Add consent_given and consent_at to users table.

Revision ID: 010
Revises: 009
Create Date: 2026-03-31
"""

import sqlalchemy as sa
from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("consent_given", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("users", sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "consent_at")
    op.drop_column("users", "consent_given")
