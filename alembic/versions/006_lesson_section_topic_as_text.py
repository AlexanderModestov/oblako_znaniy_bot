"""Replace course_id/section_id/topic_id FK columns with course/section/topic text columns in lessons.

Revision ID: 006
Revises: d5486c85a6e8
Create Date: 2026-03-23
"""

from alembic import op

revision = "006"
down_revision = "d5486c85a6e8"
branch_labels = None
depends_on = None


def upgrade():
    # Idempotent: add columns only if they don't exist, drop only if they do
    op.execute("""
        DO $$
        BEGIN
            -- Add new text columns
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='lessons' AND column_name='course') THEN
                ALTER TABLE lessons ADD COLUMN course TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='lessons' AND column_name='section') THEN
                ALTER TABLE lessons ADD COLUMN section TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='lessons' AND column_name='topic') THEN
                ALTER TABLE lessons ADD COLUMN topic TEXT;
            END IF;

            -- Copy names from related tables (only if old columns still exist)
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='lessons' AND column_name='course_id') THEN
                UPDATE lessons l SET course = c.name FROM courses c WHERE l.course_id = c.id AND l.course IS NULL;
            END IF;
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='lessons' AND column_name='section_id') THEN
                UPDATE lessons l SET section = s.name FROM sections s WHERE l.section_id = s.id AND l.section IS NULL;
            END IF;
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='lessons' AND column_name='topic_id') THEN
                UPDATE lessons l SET topic = t.name FROM topics t WHERE l.topic_id = t.id AND l.topic IS NULL;
            END IF;

            -- Drop FK constraints (ignore if already dropped)
            IF EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='fk_lessons_course_id' AND table_name='lessons') THEN
                ALTER TABLE lessons DROP CONSTRAINT fk_lessons_course_id;
            END IF;
            IF EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='fk_lessons_section_id' AND table_name='lessons') THEN
                ALTER TABLE lessons DROP CONSTRAINT fk_lessons_section_id;
            END IF;
            IF EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='fk_lessons_topic_id' AND table_name='lessons') THEN
                ALTER TABLE lessons DROP CONSTRAINT fk_lessons_topic_id;
            END IF;

            -- Drop old columns
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='lessons' AND column_name='course_id') THEN
                ALTER TABLE lessons DROP COLUMN course_id;
            END IF;
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='lessons' AND column_name='section_id') THEN
                ALTER TABLE lessons DROP COLUMN section_id;
            END IF;
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='lessons' AND column_name='topic_id') THEN
                ALTER TABLE lessons DROP COLUMN topic_id;
            END IF;
        END $$;
    """)

    # Update search vector trigger
    op.execute("DROP TRIGGER IF EXISTS lessons_search_vector_trigger ON lessons")
    op.execute("DROP FUNCTION IF EXISTS lessons_search_vector_update")

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

    # Rebuild search vectors
    op.execute("""
        UPDATE lessons SET search_vector =
            setweight(to_tsvector('russian', coalesce(title, '')), 'A') ||
            setweight(to_tsvector('russian', coalesce(description, '')), 'B') ||
            setweight(to_tsvector('russian', coalesce(section, '')), 'C') ||
            setweight(to_tsvector('russian', coalesce(topic, '')), 'C')
    """)


def downgrade():
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='lessons' AND column_name='course_id') THEN
                ALTER TABLE lessons ADD COLUMN course_id INTEGER;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='lessons' AND column_name='section_id') THEN
                ALTER TABLE lessons ADD COLUMN section_id VARCHAR(50);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='lessons' AND column_name='topic_id') THEN
                ALTER TABLE lessons ADD COLUMN topic_id VARCHAR(50);
            END IF;

            ALTER TABLE lessons DROP COLUMN IF EXISTS course;
            ALTER TABLE lessons DROP COLUMN IF EXISTS section;
            ALTER TABLE lessons DROP COLUMN IF EXISTS topic;
        END $$;
    """)

    op.execute("DROP TRIGGER IF EXISTS lessons_search_vector_trigger ON lessons")
    op.execute("DROP FUNCTION IF EXISTS lessons_search_vector_update")

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
