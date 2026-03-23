"""Replace course_id/section_id/topic_id FK columns with course/section/topic text columns in lessons.

Revision ID: 006
Revises: d5486c85a6e8
Create Date: 2026-03-23
"""

from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "d5486c85a6e8"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add new text columns
    op.add_column("lessons", sa.Column("course", sa.Text(), nullable=True))
    op.add_column("lessons", sa.Column("section", sa.Text(), nullable=True))
    op.add_column("lessons", sa.Column("topic", sa.Text(), nullable=True))

    # 2. Copy names from related tables into new columns
    op.execute("""
        UPDATE lessons l
        SET course = c.name
        FROM courses c
        WHERE l.course_id = c.id
    """)
    op.execute("""
        UPDATE lessons l
        SET section = s.name
        FROM sections s
        WHERE l.section_id = s.id
    """)
    op.execute("""
        UPDATE lessons l
        SET topic = t.name
        FROM topics t
        WHERE l.topic_id = t.id
    """)

    # 3. Drop FK constraints and old columns
    op.drop_constraint("fk_lessons_course_id", "lessons", type_="foreignkey")
    op.drop_constraint("fk_lessons_section_id", "lessons", type_="foreignkey")
    op.drop_constraint("fk_lessons_topic_id", "lessons", type_="foreignkey")
    op.drop_column("lessons", "course_id")
    op.drop_column("lessons", "section_id")
    op.drop_column("lessons", "topic_id")

    # 4. Update search vector trigger to use text columns directly
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

    # 5. Rebuild search vectors
    op.execute("""
        UPDATE lessons SET search_vector =
            setweight(to_tsvector('russian', coalesce(title, '')), 'A') ||
            setweight(to_tsvector('russian', coalesce(description, '')), 'B') ||
            setweight(to_tsvector('russian', coalesce(section, '')), 'C') ||
            setweight(to_tsvector('russian', coalesce(topic, '')), 'C')
    """)


def downgrade():
    # Restore old columns (without FK)
    op.add_column("lessons", sa.Column("course_id", sa.Integer(), nullable=True))
    op.add_column("lessons", sa.Column("section_id", sa.String(50), nullable=True))
    op.add_column("lessons", sa.Column("topic_id", sa.String(50), nullable=True))

    # Drop text columns
    op.drop_column("lessons", "course")
    op.drop_column("lessons", "section")
    op.drop_column("lessons", "topic")

    # Restore old trigger
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
