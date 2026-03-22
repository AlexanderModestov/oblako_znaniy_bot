"""normalize schema: municipalities, courses, sections, topics, lesson_links

Revision ID: 004
Revises: f67ac08d8d80
Create Date: 2026-03-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "f67ac08d8d80"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- New tables ---

    op.create_table(
        "municipalities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(["region_id"], ["regions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("region_id", "name", name="uq_municipalities_region_id_name"),
    )

    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("actual", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        sa.Column("demo_link", sa.Text(), nullable=True),
        sa.Column("methodology_link", sa.Text(), nullable=True),
        sa.Column("standard", sa.Text(), nullable=True),
        sa.Column("skills", sa.Text(), nullable=True),
        sa.Column("deleted", sa.Boolean(), nullable=True, server_default=sa.text("false")),
        sa.Column("status_msh", sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "sections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("actual", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        sa.Column("demo_link", sa.Text(), nullable=True),
        sa.Column("methodology_link", sa.Text(), nullable=True),
        sa.Column("standard", sa.Text(), nullable=True),
        sa.Column("skills", sa.Text(), nullable=True),
        sa.Column("deleted", sa.Boolean(), nullable=True, server_default=sa.text("false")),
        sa.Column("status_msh", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "topics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("section_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("actual", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        sa.Column("demo_link", sa.Text(), nullable=True),
        sa.Column("methodology_link", sa.Text(), nullable=True),
        sa.Column("skills", sa.Text(), nullable=True),
        sa.Column("deleted", sa.Boolean(), nullable=True, server_default=sa.text("false")),
        sa.Column("status_msh", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["section_id"], ["sections.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "lesson_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- Modify subjects: add code column ---

    op.add_column("subjects", sa.Column("code", sa.String(length=50), nullable=True))

    # --- Modify lessons ---

    op.add_column("lessons", sa.Column("course_id", sa.Integer(), nullable=True))
    op.add_column("lessons", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("lessons", sa.Column("section_id", sa.Integer(), nullable=True))
    op.add_column("lessons", sa.Column("topic_id", sa.Integer(), nullable=True))

    op.create_foreign_key("fk_lessons_course_id", "lessons", "courses", ["course_id"], ["id"])
    op.create_foreign_key("fk_lessons_section_id", "lessons", "sections", ["section_id"], ["id"])
    op.create_foreign_key("fk_lessons_topic_id", "lessons", "topics", ["topic_id"], ["id"])

    op.drop_column("lessons", "section")
    op.drop_column("lessons", "topic")
    op.drop_column("lessons", "lesson_type")

    # --- Modify schools ---

    # Drop constraint and old column, add new municipality_id
    op.drop_constraint("uq_schools_region_id_name", "schools", type_="unique")
    op.drop_column("schools", "region_id")
    op.add_column(
        "schools",
        sa.Column("municipality_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_schools_municipality_id", "schools", "municipalities",
        ["municipality_id"], ["id"],
    )
    op.create_unique_constraint(
        "uq_schools_municipality_id_name", "schools",
        ["municipality_id", "name"],
    )

    # --- Update search vector trigger ---

    op.execute("DROP TRIGGER IF EXISTS lessons_search_vector_trigger ON lessons")
    op.execute("DROP FUNCTION IF EXISTS lessons_search_vector_update")
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


def downgrade() -> None:
    # --- Restore search vector trigger to original (title + section + topic) ---

    op.execute("DROP TRIGGER IF EXISTS lessons_search_vector_trigger ON lessons")
    op.execute("DROP FUNCTION IF EXISTS lessons_search_vector_update")
    op.execute("""
        CREATE OR REPLACE FUNCTION lessons_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('russian', coalesce(NEW.title, '')), 'A') ||
                setweight(to_tsvector('russian', coalesce(NEW.section, '')), 'B') ||
                setweight(to_tsvector('russian', coalesce(NEW.topic, '')), 'B');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER lessons_search_vector_trigger
            BEFORE INSERT OR UPDATE ON lessons
            FOR EACH ROW EXECUTE FUNCTION lessons_search_vector_update()
    """)

    # --- Restore schools ---

    op.drop_constraint("uq_schools_municipality_id_name", "schools", type_="unique")
    op.drop_constraint("fk_schools_municipality_id", "schools", type_="foreignkey")
    op.drop_column("schools", "municipality_id")
    op.add_column(
        "schools",
        sa.Column("region_id", sa.Integer(), nullable=False),
    )
    op.create_foreign_key(None, "schools", "regions", ["region_id"], ["id"])
    op.create_unique_constraint("uq_schools_region_id_name", "schools", ["region_id", "name"])

    # --- Restore lessons ---

    op.add_column("lessons", sa.Column("section", sa.String(length=255), nullable=True))
    op.add_column("lessons", sa.Column("topic", sa.String(length=255), nullable=True))
    op.add_column("lessons", sa.Column("lesson_type", sa.String(length=255), nullable=True))

    op.drop_constraint("fk_lessons_topic_id", "lessons", type_="foreignkey")
    op.drop_constraint("fk_lessons_section_id", "lessons", type_="foreignkey")
    op.drop_constraint("fk_lessons_course_id", "lessons", type_="foreignkey")

    op.drop_column("lessons", "topic_id")
    op.drop_column("lessons", "section_id")
    op.drop_column("lessons", "description")
    op.drop_column("lessons", "course_id")

    # --- Restore subjects ---

    op.drop_column("subjects", "code")

    # --- Drop new tables (reverse order) ---

    op.drop_table("lesson_links")
    op.drop_table("topics")
    op.drop_table("sections")
    op.drop_table("courses")
    op.drop_table("municipalities")
