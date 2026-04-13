"""Narrow search_vector to title-only.

Revision ID: 011
Revises: 010
Create Date: 2026-04-13
"""

from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS lessons_search_vector_trigger ON lessons")
    op.execute("DROP FUNCTION IF EXISTS lessons_search_vector_update CASCADE")

    op.execute("""
        CREATE OR REPLACE FUNCTION lessons_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector := to_tsvector('russian', coalesce(NEW.title, ''));
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER lessons_search_vector_trigger
            BEFORE INSERT OR UPDATE ON lessons
            FOR EACH ROW EXECUTE FUNCTION lessons_search_vector_update()
    """)

    op.execute("""
        UPDATE lessons SET search_vector =
            to_tsvector('russian', coalesce(title, ''))
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS lessons_search_vector_trigger ON lessons")
    op.execute("DROP FUNCTION IF EXISTS lessons_search_vector_update CASCADE")

    op.execute("""
        CREATE OR REPLACE FUNCTION lessons_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('russian', coalesce(NEW.title, '')), 'A') ||
                setweight(to_tsvector('russian', coalesce(NEW.description, '')), 'B') ||
                setweight(to_tsvector('russian', coalesce(NEW.section, '')), 'C') ||
                setweight(to_tsvector('russian', coalesce(NEW.topic, '')), 'C');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER lessons_search_vector_trigger
            BEFORE INSERT OR UPDATE ON lessons
            FOR EACH ROW EXECUTE FUNCTION lessons_search_vector_update()
    """)

    op.execute("""
        UPDATE lessons SET search_vector =
            setweight(to_tsvector('russian', coalesce(title, '')), 'A') ||
            setweight(to_tsvector('russian', coalesce(description, '')), 'B') ||
            setweight(to_tsvector('russian', coalesce(section, '')), 'C') ||
            setweight(to_tsvector('russian', coalesce(topic, '')), 'C')
    """)
