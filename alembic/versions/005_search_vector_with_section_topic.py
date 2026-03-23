"""Update search vector trigger to include section and topic names.

Revision ID: 005
Revises: 004
Create Date: 2026-03-23
"""

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade():
    # Drop old trigger and function
    op.execute("DROP TRIGGER IF EXISTS lessons_search_vector_trigger ON lessons")
    op.execute("DROP FUNCTION IF EXISTS lessons_search_vector_update")

    # New trigger function: looks up section/topic names via subselect
    op.execute("""
        CREATE OR REPLACE FUNCTION lessons_search_vector_update() RETURNS trigger AS $$
        DECLARE
            _section_name TEXT := '';
            _topic_name TEXT := '';
        BEGIN
            IF NEW.section_id IS NOT NULL THEN
                SELECT name INTO _section_name FROM sections WHERE id = NEW.section_id;
            END IF;
            IF NEW.topic_id IS NOT NULL THEN
                SELECT name INTO _topic_name FROM topics WHERE id = NEW.topic_id;
            END IF;
            NEW.search_vector :=
                setweight(to_tsvector('russian', coalesce(NEW.title, '')), 'A') ||
                setweight(to_tsvector('russian', coalesce(NEW.description, '')), 'B') ||
                setweight(to_tsvector('russian', coalesce(_section_name, '')), 'C') ||
                setweight(to_tsvector('russian', coalesce(_topic_name, '')), 'C');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER lessons_search_vector_trigger
            BEFORE INSERT OR UPDATE ON lessons
            FOR EACH ROW EXECUTE FUNCTION lessons_search_vector_update()
    """)

    # Rebuild search_vector for all existing lessons
    op.execute("""
        UPDATE lessons SET search_vector =
            setweight(to_tsvector('russian', coalesce(lessons.title, '')), 'A') ||
            setweight(to_tsvector('russian', coalesce(lessons.description, '')), 'B') ||
            setweight(to_tsvector('russian', coalesce(s.name, '')), 'C') ||
            setweight(to_tsvector('russian', coalesce(t.name, '')), 'C')
        FROM lessons l2
        LEFT JOIN sections s ON l2.section_id = s.id
        LEFT JOIN topics t ON l2.topic_id = t.id
        WHERE lessons.id = l2.id
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS lessons_search_vector_trigger ON lessons")
    op.execute("DROP FUNCTION IF EXISTS lessons_search_vector_update")

    # Restore previous version (title + description only)
    op.execute("""
        CREATE OR REPLACE FUNCTION lessons_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('russian', coalesce(NEW.title, '')), 'A') ||
                setweight(to_tsvector('russian', coalesce(NEW.description, '')), 'B');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER lessons_search_vector_trigger
            BEFORE INSERT OR UPDATE ON lessons
            FOR EACH ROW EXECUTE FUNCTION lessons_search_vector_update()
    """)
