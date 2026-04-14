"""Enable pg_trgm and add trigram index on lessons.title.

Revision ID: 012
Revises: 011
Create Date: 2026-04-14
"""

from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS lessons_title_trgm_idx "
        "ON lessons USING GIN (title gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS lessons_title_trgm_idx")
