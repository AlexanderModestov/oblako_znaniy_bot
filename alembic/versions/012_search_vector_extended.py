"""Extend search_vector to title + description + subject.name + grade with weights.

Revision ID: 012
Revises: 011
Create Date: 2026-04-15
"""

from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS lessons_search_vector_trigger ON lessons")
    op.execute("DROP FUNCTION IF EXISTS lessons_search_vector_update CASCADE")

    op.execute("""
        CREATE OR REPLACE FUNCTION lessons_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('russian', coalesce(NEW.title, '')), 'A') ||
                setweight(to_tsvector('russian',
                    coalesce((SELECT name FROM subjects WHERE id = NEW.subject_id), '')
                ), 'B') ||
                setweight(to_tsvector('russian', coalesce(NEW.grade::text, '')), 'B') ||
                setweight(to_tsvector('russian', coalesce(NEW.description, '')), 'C');
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
            setweight(to_tsvector('russian',
                coalesce((SELECT name FROM subjects WHERE id = lessons.subject_id), '')
            ), 'B') ||
            setweight(to_tsvector('russian', coalesce(grade::text, '')), 'B') ||
            setweight(to_tsvector('russian', coalesce(description, '')), 'C')
    """)


def downgrade() -> None:
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
