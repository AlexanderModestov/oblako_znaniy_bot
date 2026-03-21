"""Enable pgvector extension and create search_vector trigger.

Revision ID: 001
Revises:
Create Date: 2026-03-21
"""

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    op.execute("""
        CREATE OR REPLACE FUNCTION lessons_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('russian', coalesce(NEW.title, '')), 'A') ||
                setweight(to_tsvector('russian', coalesce(NEW.section, '')), 'B') ||
                setweight(to_tsvector('russian', coalesce(NEW.topic, '')), 'B');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER lessons_search_vector_trigger
            BEFORE INSERT OR UPDATE ON lessons
            FOR EACH ROW EXECUTE FUNCTION lessons_search_vector_update();
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS lessons_search_vector_trigger ON lessons;")
    op.execute("DROP FUNCTION IF EXISTS lessons_search_vector_update;")
    op.execute("DROP EXTENSION IF EXISTS vector;")
