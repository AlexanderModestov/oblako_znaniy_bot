# Database Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restructure the database from flat lesson model to normalized hierarchy (Course → Section → Topic → Lesson), add Municipality entity, and update the data loader.

**Architecture:** New SQLAlchemy ORM models for Municipality, Course, Section, Topic, LessonLink. Alembic migration to alter existing tables and create new ones. Loader refactored to load data from 7 Google Sheets tabs in FK-dependency order. Search trigger updated to use title + description instead of denormalized section/topic text.

**Tech Stack:** SQLAlchemy 2.0 (async), Alembic, gspread, PostgreSQL 16 + pgvector

---

### Task 1: Update ORM Models

**Files:**
- Modify: `src/core/models.py`

**Step 1: Add Municipality model and update School model**

Replace the entire `src/core/models.py` with the updated models. Key changes:
- Add `Municipality` model (id, region_id FK, name, unique constraint)
- `School`: replace `region_id` with `municipality_id` FK, update unique constraint
- `Subject`: add `code` field
- Add `Course` model (id, name, description, actual, demo_link, methodology_link, standard, skills, deleted, status_msh)
- Add `Section` model (id, course_id FK, name, description, actual, demo_link, methodology_link, standard, skills, deleted, status_msh)
- Add `Topic` model (id, section_id FK, name, description, actual, demo_link, methodology_link, skills, deleted, status_msh)
- `Lesson`: replace `section`/`topic` text fields with `section_id`/`topic_id` FKs, add `course_id` FK, add `description`, remove `lesson_type`
- Add `LessonLink` model (id, lesson_id FK, url)

```python
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class Region(Base):
    __tablename__ = "regions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    municipalities: Mapped[list["Municipality"]] = relationship(back_populates="region")


class Municipality(Base):
    __tablename__ = "municipalities"
    __table_args__ = (UniqueConstraint("region_id", "name", name="uq_municipalities_region_id_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    region: Mapped["Region"] = relationship(back_populates="municipalities")
    schools: Mapped[list["School"]] = relationship(back_populates="municipality")


class School(Base):
    __tablename__ = "schools"
    __table_args__ = (UniqueConstraint("municipality_id", "name", name="uq_schools_municipality_id_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    municipality: Mapped["Municipality"] = relationship(back_populates="schools")


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual: Mapped[bool] = mapped_column(Boolean, default=True)
    demo_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    methodology_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    standard: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    status_msh: Mapped[str | None] = mapped_column(String(100), nullable=True)

    sections: Mapped[list["Section"]] = relationship(back_populates="course")


class Section(Base):
    __tablename__ = "sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual: Mapped[bool] = mapped_column(Boolean, default=True)
    demo_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    methodology_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    standard: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    status_msh: Mapped[str | None] = mapped_column(String(100), nullable=True)

    course: Mapped["Course"] = relationship(back_populates="sections")
    topics: Mapped[list["Topic"]] = relationship(back_populates="section")


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual: Mapped[bool] = mapped_column(Boolean, default=True)
    demo_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    methodology_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    status_msh: Mapped[str | None] = mapped_column(String(100), nullable=True)

    section: Mapped["Section"] = relationship(back_populates="topics")


class Lesson(Base):
    __tablename__ = "lessons"
    __table_args__ = (
        Index("ix_lessons_subject_grade", "subject_id", "grade"),
        Index("ix_lessons_search_vector", "search_vector", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), nullable=False)
    grade: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id"), nullable=True)
    section_id: Mapped[int | None] = mapped_column(ForeignKey("sections.id"), nullable=True)
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)
    embedding = mapped_column(Vector(1536), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    subject: Mapped["Subject"] = relationship()
    course: Mapped["Course | None"] = relationship()
    section: Mapped["Section | None"] = relationship()
    topic: Mapped["Topic | None"] = relationship()
    links: Mapped[list["LessonLink"]] = relationship(back_populates="lesson")


class LessonLink(Base):
    __tablename__ = "lesson_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)

    lesson: Mapped["Lesson"] = relationship(back_populates="links")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"), nullable=False)
    subjects: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger), default=list)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    region: Mapped["Region"] = relationship()
    school: Mapped["School"] = relationship()
```

**Step 2: Verify models import without errors**

Run: `python -c "from src.core.models import Region, Municipality, School, Subject, Course, Section, Topic, Lesson, LessonLink, User; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add src/core/models.py
git commit -m "refactor: normalize database models - add Municipality, Course, Section, Topic, LessonLink"
```

---

### Task 2: Create Alembic Migration

**Files:**
- Create: `alembic/versions/004_normalize_schema.py`
- Modify: `alembic/env.py` (update imports)

**Step 1: Update alembic env.py imports**

In `alembic/env.py`, change line 5:
```python
# Old:
from src.core.models import Region, School, Subject, User, Lesson  # noqa: F401
# New:
from src.core.models import (  # noqa: F401
    Region, Municipality, School, Subject, Course, Section, Topic,
    Lesson, LessonLink, User,
)
```

**Step 2: Write the migration**

Create `alembic/versions/004_normalize_schema.py`:

```python
"""Normalize schema: add Municipality, Course, Section, Topic, LessonLink.

Revision ID: 004
Revises: f67ac08d8d80
Create Date: 2026-03-22
"""

import sqlalchemy as sa
from alembic import op

revision = "004"
down_revision = "f67ac08d8d80"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create new tables
    op.create_table(
        "municipalities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("region_id", sa.Integer(), sa.ForeignKey("regions.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.UniqueConstraint("region_id", "name", name="uq_municipalities_region_id_name"),
    )

    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("actual", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("demo_link", sa.Text(), nullable=True),
        sa.Column("methodology_link", sa.Text(), nullable=True),
        sa.Column("standard", sa.Text(), nullable=True),
        sa.Column("skills", sa.Text(), nullable=True),
        sa.Column("deleted", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("status_msh", sa.String(100), nullable=True),
    )

    op.create_table(
        "sections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("actual", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("demo_link", sa.Text(), nullable=True),
        sa.Column("methodology_link", sa.Text(), nullable=True),
        sa.Column("standard", sa.Text(), nullable=True),
        sa.Column("skills", sa.Text(), nullable=True),
        sa.Column("deleted", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("status_msh", sa.String(100), nullable=True),
    )

    op.create_table(
        "topics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("section_id", sa.Integer(), sa.ForeignKey("sections.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("actual", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("demo_link", sa.Text(), nullable=True),
        sa.Column("methodology_link", sa.Text(), nullable=True),
        sa.Column("skills", sa.Text(), nullable=True),
        sa.Column("deleted", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("status_msh", sa.String(100), nullable=True),
    )

    op.create_table(
        "lesson_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lesson_id", sa.Integer(), sa.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
    )

    # 2. Modify subjects: add code column
    op.add_column("subjects", sa.Column("code", sa.String(50), nullable=True))

    # 3. Modify lessons: add new FK columns, add description, drop old text columns
    op.add_column("lessons", sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id"), nullable=True))
    op.add_column("lessons", sa.Column("description", sa.Text(), nullable=True))

    # Drop old text columns (section, topic, lesson_type) and replace with FK IDs
    # section_id and topic_id will replace the text fields
    op.drop_column("lessons", "section")
    op.drop_column("lessons", "topic")
    op.drop_column("lessons", "lesson_type")
    op.add_column("lessons", sa.Column("section_id", sa.Integer(), sa.ForeignKey("sections.id"), nullable=True))
    op.add_column("lessons", sa.Column("topic_id", sa.Integer(), sa.ForeignKey("topics.id"), nullable=True))

    # 4. Modify schools: replace region_id with municipality_id
    op.drop_constraint("uq_schools_region_id_name", "schools", type_="unique")
    op.drop_column("schools", "region_id")
    op.add_column("schools", sa.Column("municipality_id", sa.Integer(), sa.ForeignKey("municipalities.id"), nullable=False))
    op.create_unique_constraint("uq_schools_municipality_id_name", "schools", ["municipality_id", "name"])

    # 5. Update search vector trigger to use title + description
    op.execute("DROP TRIGGER IF EXISTS lessons_search_vector_trigger ON lessons;")
    op.execute("DROP FUNCTION IF EXISTS lessons_search_vector_update;")
    op.execute("""
        CREATE OR REPLACE FUNCTION lessons_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('russian', coalesce(NEW.title, '')), 'A') ||
                setweight(to_tsvector('russian', coalesce(NEW.description, '')), 'B');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER lessons_search_vector_trigger
            BEFORE INSERT OR UPDATE ON lessons
            FOR EACH ROW EXECUTE FUNCTION lessons_search_vector_update();
    """)


def downgrade():
    # Reverse trigger
    op.execute("DROP TRIGGER IF EXISTS lessons_search_vector_trigger ON lessons;")
    op.execute("DROP FUNCTION IF EXISTS lessons_search_vector_update;")
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

    # Reverse schools
    op.drop_constraint("uq_schools_municipality_id_name", "schools", type_="unique")
    op.drop_column("schools", "municipality_id")
    op.add_column("schools", sa.Column("region_id", sa.Integer(), sa.ForeignKey("regions.id"), nullable=False))
    op.create_unique_constraint("uq_schools_region_id_name", "schools", ["region_id", "name"])

    # Reverse lessons
    op.drop_column("lessons", "topic_id")
    op.drop_column("lessons", "section_id")
    op.add_column("lessons", sa.Column("lesson_type", sa.String(255), nullable=True))
    op.add_column("lessons", sa.Column("topic", sa.String(255), nullable=True))
    op.add_column("lessons", sa.Column("section", sa.String(255), nullable=True))
    op.drop_column("lessons", "description")
    op.drop_column("lessons", "course_id")

    # Reverse subjects
    op.drop_column("subjects", "code")

    # Drop new tables (reverse order)
    op.drop_table("lesson_links")
    op.drop_table("topics")
    op.drop_table("sections")
    op.drop_table("courses")
    op.drop_table("municipalities")
```

**Step 3: Commit**

```bash
git add alembic/env.py alembic/versions/004_normalize_schema.py
git commit -m "feat: add migration 004 - normalize schema with municipalities, courses, sections, topics"
```

---

### Task 3: Rewrite the Data Loader

**Files:**
- Modify: `src/core/services/loader.py`

**Step 1: Rewrite loader with all fetch and reload functions**

The loader needs these new functions:
- `fetch_schools_from_sheets()` → read all tabs except first, combine into one list
- `fetch_subjects_from_sheets()` → read "subject" tab
- `fetch_courses_from_sheets()` → read "Курс" tab
- `fetch_sections_from_sheets()` → read "Разделы" tab
- `fetch_topics_from_sheets()` → read "Темы" tab
- `fetch_lessons_from_sheets()` → read "Уроки" tab
- `fetch_lesson_links_from_sheets()` → read "Ссылки" tab
- `reload_schools_data(session)` → regions + municipalities + schools upsert
- `reload_subjects_data(session)` → subjects upsert with code
- `reload_courses_data(session)` → courses upsert
- `reload_sections_data(session)` → sections upsert
- `reload_topics_data(session)` → topics upsert
- `reload_lessons_data(session)` → delete all + batch insert
- `reload_lesson_links_data(session)` → delete all + batch insert

```python
import json
import logging

import gspread
from google.oauth2.service_account import Credentials
from openai import AsyncOpenAI
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.core.models import (
    Course, Lesson, LessonLink, Municipality, Region, School, Section, Subject, Topic,
)

logger = logging.getLogger(__name__)


def _get_gspread_client() -> gspread.Client:
    settings = get_settings()
    creds_dict = json.loads(settings.google_service_account_json)
    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    return gspread.authorize(creds)


# ---------- Fetch from Google Sheets ----------

def fetch_schools_from_sheets() -> list[dict]:
    """Read all tabs except the first from the schools spreadsheet."""
    settings = get_settings()
    client = _get_gspread_client()
    spreadsheet = client.open_by_key(settings.google_sheets_schools_id)
    all_rows = []
    for worksheet in spreadsheet.worksheets()[1:]:  # skip first tab
        rows = worksheet.get_all_records()
        all_rows.extend(rows)
    return all_rows


def fetch_subjects_from_sheets() -> list[dict]:
    settings = get_settings()
    client = _get_gspread_client()
    spreadsheet = client.open_by_key(settings.google_sheets_lessons_id)
    return spreadsheet.worksheet("subject").get_all_records()


def fetch_courses_from_sheets() -> list[dict]:
    settings = get_settings()
    client = _get_gspread_client()
    spreadsheet = client.open_by_key(settings.google_sheets_lessons_id)
    return spreadsheet.worksheet("Курс").get_all_records()


def fetch_sections_from_sheets() -> list[dict]:
    settings = get_settings()
    client = _get_gspread_client()
    spreadsheet = client.open_by_key(settings.google_sheets_lessons_id)
    return spreadsheet.worksheet("Разделы").get_all_records()


def fetch_topics_from_sheets() -> list[dict]:
    settings = get_settings()
    client = _get_gspread_client()
    spreadsheet = client.open_by_key(settings.google_sheets_lessons_id)
    return spreadsheet.worksheet("Темы").get_all_records()


def fetch_lessons_from_sheets() -> list[dict]:
    settings = get_settings()
    client = _get_gspread_client()
    spreadsheet = client.open_by_key(settings.google_sheets_lessons_id)
    return spreadsheet.worksheet("Уроки").get_all_records()


def fetch_lesson_links_from_sheets() -> list[dict]:
    settings = get_settings()
    client = _get_gspread_client()
    spreadsheet = client.open_by_key(settings.google_sheets_lessons_id)
    return spreadsheet.worksheet("Ссылки").get_all_records()


# ---------- Parse helpers ----------

def _str(row: dict, key: str) -> str:
    return str(row.get(key, "")).strip()


def _int_or_none(row: dict, key: str) -> int | None:
    val = _str(row, key)
    if not val:
        return None
    try:
        return int(val)
    except ValueError:
        return None


def _bool_field(row: dict, key: str) -> bool:
    val = _str(row, key).lower()
    return val in ("1", "true", "да", "yes")


# ---------- Reload functions ----------

async def reload_schools_data(session: AsyncSession) -> dict:
    """Load regions, municipalities, and schools from Google Sheets."""
    rows = fetch_schools_from_sheets()

    # Collect unique regions and municipalities
    regions_set = set()
    municipalities_set = set()  # (region_name, municipality_name)
    schools_list = []

    for row in rows:
        region = _str(row, "Регион")
        municipality = _str(row, "Наименование муниципалитета")
        school = _str(row, "Школа")
        if region and school:
            regions_set.add(region)
            if municipality:
                municipalities_set.add((region, municipality))
            schools_list.append({
                "region": region,
                "municipality": municipality,
                "school": school,
            })

    # Upsert regions
    if regions_set:
        stmt = pg_insert(Region).values([{"name": n} for n in regions_set])
        stmt = stmt.on_conflict_do_nothing(index_elements=["name"])
        await session.execute(stmt)
        await session.flush()

    result = await session.execute(select(Region))
    region_map = {r.name: r.id for r in result.scalars().all()}

    # Upsert municipalities
    if municipalities_set:
        muni_values = [
            {"region_id": region_map[r], "name": m}
            for r, m in municipalities_set
            if r in region_map
        ]
        if muni_values:
            stmt = pg_insert(Municipality).values(muni_values)
            stmt = stmt.on_conflict_do_nothing(constraint="uq_municipalities_region_id_name")
            await session.execute(stmt)
            await session.flush()

    result = await session.execute(select(Municipality))
    muni_map = {(m.region_id, m.name): m.id for m in result.scalars().all()}

    # Upsert schools in chunks
    school_values = []
    for item in schools_list:
        region_id = region_map.get(item["region"])
        if region_id:
            muni_id = muni_map.get((region_id, item["municipality"]))
            if muni_id:
                school_values.append({"municipality_id": muni_id, "name": item["school"]})

    for i in range(0, len(school_values), 500):
        batch = school_values[i : i + 500]
        stmt = pg_insert(School).values(batch)
        stmt = stmt.on_conflict_do_nothing(constraint="uq_schools_municipality_id_name")
        await session.execute(stmt)

    await session.commit()
    return {
        "regions": len(regions_set),
        "municipalities": len(municipalities_set),
        "schools": len(school_values),
    }


async def reload_subjects_data(session: AsyncSession) -> dict:
    """Load subjects from Google Sheets 'subject' tab."""
    rows = fetch_subjects_from_sheets()
    values = []
    for row in rows:
        name = _str(row, "Name")
        if name:
            values.append({
                "name": name,
                "code": _str(row, "Code") or None,
            })

    if values:
        stmt = pg_insert(Subject).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["name"],
            set_={"code": stmt.excluded.code},
        )
        await session.execute(stmt)
        await session.commit()

    return {"subjects": len(values)}


async def reload_courses_data(session: AsyncSession) -> dict:
    """Load courses from Google Sheets 'Курс' tab."""
    rows = fetch_courses_from_sheets()
    values = []
    for row in rows:
        course_id = _int_or_none(row, "ИД курса")
        name = _str(row, "Наименование")
        if course_id and name:
            values.append({
                "id": course_id,
                "name": name,
                "description": _str(row, "Описание") or None,
                "actual": _bool_field(row, "Актуальность"),
                "demo_link": _str(row, "Ссылка на демо") or None,
                "methodology_link": _str(row, "Ссылка на методичку") or None,
                "standard": _str(row, "Стандарты") or None,
                "skills": _str(row, "Навыки") or None,
                "deleted": _bool_field(row, "Удалено"),
                "status_msh": _str(row, "Статус МШ") or None,
            })

    for i in range(0, len(values), 500):
        batch = values[i : i + 500]
        stmt = pg_insert(Course).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "name": stmt.excluded.name,
                "description": stmt.excluded.description,
                "actual": stmt.excluded.actual,
                "demo_link": stmt.excluded.demo_link,
                "methodology_link": stmt.excluded.methodology_link,
                "standard": stmt.excluded.standard,
                "skills": stmt.excluded.skills,
                "deleted": stmt.excluded.deleted,
                "status_msh": stmt.excluded.status_msh,
            },
        )
        await session.execute(stmt)

    await session.commit()
    return {"courses": len(values)}


async def reload_sections_data(session: AsyncSession) -> dict:
    """Load sections from Google Sheets 'Разделы' tab."""
    rows = fetch_sections_from_sheets()
    values = []
    for row in rows:
        section_id = _int_or_none(row, "ИД раздела")
        course_id = _int_or_none(row, "ИД курса")
        name = _str(row, "Наименование")
        if section_id and course_id and name:
            values.append({
                "id": section_id,
                "course_id": course_id,
                "name": name,
                "description": _str(row, "Описание") or None,
                "actual": _bool_field(row, "Актуальность"),
                "demo_link": _str(row, "Ссылка на демо") or None,
                "methodology_link": _str(row, "Ссылка на методичку") or None,
                "standard": _str(row, "Стандарты") or None,
                "skills": _str(row, "Навыки") or None,
                "deleted": _bool_field(row, "Удалено"),
                "status_msh": _str(row, "Статус МШ") or None,
            })

    for i in range(0, len(values), 500):
        batch = values[i : i + 500]
        stmt = pg_insert(Section).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "course_id": stmt.excluded.course_id,
                "name": stmt.excluded.name,
                "description": stmt.excluded.description,
                "actual": stmt.excluded.actual,
                "demo_link": stmt.excluded.demo_link,
                "methodology_link": stmt.excluded.methodology_link,
                "standard": stmt.excluded.standard,
                "skills": stmt.excluded.skills,
                "deleted": stmt.excluded.deleted,
                "status_msh": stmt.excluded.status_msh,
            },
        )
        await session.execute(stmt)

    await session.commit()
    return {"sections": len(values)}


async def reload_topics_data(session: AsyncSession) -> dict:
    """Load topics from Google Sheets 'Темы' tab."""
    rows = fetch_topics_from_sheets()
    values = []
    for row in rows:
        topic_id = _int_or_none(row, "ИД темы")
        section_id = _int_or_none(row, "ИД раздела")
        name = _str(row, "Наименование")
        if topic_id and section_id and name:
            values.append({
                "id": topic_id,
                "section_id": section_id,
                "name": name,
                "description": _str(row, "Описание") or None,
                "actual": _bool_field(row, "Актуальность"),
                "demo_link": _str(row, "Ссылка на демо") or None,
                "methodology_link": _str(row, "Ссылка на методичку") or None,
                "skills": _str(row, "Навыки") or None,
                "deleted": _bool_field(row, "Удалено"),
                "status_msh": _str(row, "Статус МШ") or None,
            })

    for i in range(0, len(values), 500):
        batch = values[i : i + 500]
        stmt = pg_insert(Topic).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "section_id": stmt.excluded.section_id,
                "name": stmt.excluded.name,
                "description": stmt.excluded.description,
                "actual": stmt.excluded.actual,
                "demo_link": stmt.excluded.demo_link,
                "methodology_link": stmt.excluded.methodology_link,
                "skills": stmt.excluded.skills,
                "deleted": stmt.excluded.deleted,
                "status_msh": stmt.excluded.status_msh,
            },
        )
        await session.execute(stmt)

    await session.commit()
    return {"topics": len(values)}


async def reload_lessons_data(session: AsyncSession) -> dict:
    """Load lessons from Google Sheets 'Уроки' tab. Full reload (delete + insert)."""
    logger.info("Fetching lessons from Google Sheets...")
    rows = fetch_lessons_from_sheets()

    # Build subject map
    result = await session.execute(select(Subject))
    subject_map = {s.name: s.id for s in result.scalars().all()}

    # Parse rows
    lessons = []
    errors = []
    for i, row in enumerate(rows, start=2):
        subject_name = _str(row, "Предмет")
        title = _str(row, "Урок")
        url = _str(row, "Ссылка УБ ЦОК")
        grade = _int_or_none(row, "Класс")

        if not (subject_name and title and url and grade is not None):
            errors.append(i)
            continue

        subject_id = subject_map.get(subject_name)
        if not subject_id:
            logger.warning("Row %d: unknown subject '%s'", i, subject_name)
            errors.append(i)
            continue

        lessons.append({
            "id": _int_or_none(row, "ИД урока"),
            "subject_id": subject_id,
            "grade": grade,
            "course_id": _int_or_none(row, "Курс"),
            "section_id": _int_or_none(row, "Раздел"),
            "topic_id": _int_or_none(row, "Тема"),
            "title": title,
            "url": url,
            "description": _str(row, "Описание урока") or None,
        })

    logger.info("Parsed %d lessons, %d errors", len(lessons), len(errors))

    # Delete all existing lessons (cascades to lesson_links)
    await session.execute(delete(LessonLink))
    await session.execute(delete(Lesson))

    # Generate embeddings
    texts = [
        " ".join(filter(None, [l["title"], l.get("description", "")]))
        for l in lessons
    ]
    try:
        logger.info("Generating embeddings for %d lessons...", len(texts))
        embeddings = await generate_embeddings(texts)
    except Exception:
        logger.exception("Failed to generate embeddings")
        embeddings = [None] * len(lessons)

    # Batch insert
    for i in range(0, len(lessons), 500):
        batch = lessons[i : i + 500]
        batch_embeddings = embeddings[i : i + 500]
        values = [{**lesson, "embedding": batch_embeddings[j]} for j, lesson in enumerate(batch)]
        await session.execute(Lesson.__table__.insert(), values)
        logger.info("Inserted lessons %d-%d of %d", i + 1, min(i + 500, len(lessons)), len(lessons))

    await session.commit()
    return {
        "loaded": len(lessons),
        "errors": len(errors),
        "error_rows": errors,
        "embeddings": embeddings[0] is not None if embeddings else False,
    }


async def reload_lesson_links_data(session: AsyncSession) -> dict:
    """Load lesson links from Google Sheets 'Ссылки' tab. Full reload."""
    rows = fetch_lesson_links_from_sheets()

    await session.execute(delete(LessonLink))

    values = []
    for row in rows:
        lesson_id = _int_or_none(row, "ИД урока")
        url = _str(row, "URL  в УБ ЦОК")  # note: double space in header
        if lesson_id and url:
            values.append({"lesson_id": lesson_id, "url": url})

    for i in range(0, len(values), 500):
        batch = values[i : i + 500]
        await session.execute(LessonLink.__table__.insert(), batch)

    await session.commit()
    return {"links": len(values)}


async def generate_embeddings(texts: list[str]) -> list[list[float]]:
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    embeddings = []
    batch_size = 2048
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = await client.embeddings.create(
            model="text-embedding-3-small",
            input=batch,
        )
        embeddings.extend([item.embedding for item in response.data])
    return embeddings
```

**Step 2: Verify loader imports**

Run: `python -c "from src.core.services.loader import reload_schools_data, reload_subjects_data, reload_courses_data, reload_sections_data, reload_topics_data, reload_lessons_data, reload_lesson_links_data; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add src/core/services/loader.py
git commit -m "feat: rewrite loader for normalized schema with 7 Google Sheets tabs"
```

---

### Task 4: Update Admin Handler

**Files:**
- Modify: `src/telegram/handlers/admin.py`

**Step 1: Update the reload command to load all entities in order**

```python
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.config import get_settings
from src.core.services.loader import (
    reload_courses_data,
    reload_lesson_links_data,
    reload_lessons_data,
    reload_schools_data,
    reload_sections_data,
    reload_subjects_data,
    reload_topics_data,
)
from src.core.services.user import UserService

router = Router()
logger = logging.getLogger(__name__)
user_service = UserService()


def is_admin(user_id: int) -> bool:
    return user_id in get_settings().admin_ids


@router.message(Command("reload"))
async def cmd_reload(message: Message, session):
    logger.info("Reload requested by user_id=%s", message.from_user.id)
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет прав для этой команды.")
        return

    await message.answer("\u23f3 Загрузка данных...")

    # Step 1: Schools hierarchy
    try:
        schools_result = await reload_schools_data(session)
        await message.answer(
            f"\u2705 Регионы: {schools_result['regions']}, "
            f"муниципалитеты: {schools_result['municipalities']}, "
            f"школы: {schools_result['schools']}"
        )
    except Exception as e:
        logger.exception("Failed to reload schools")
        await message.answer(f"\u274c Ошибка загрузки школ: {e}")
        return

    # Step 2: Subjects
    try:
        subjects_result = await reload_subjects_data(session)
        await message.answer(f"\u2705 Предметы: {subjects_result['subjects']}")
    except Exception as e:
        logger.exception("Failed to reload subjects")
        await message.answer(f"\u274c Ошибка загрузки предметов: {e}")
        return

    # Step 3: Courses
    try:
        courses_result = await reload_courses_data(session)
        await message.answer(f"\u2705 Курсы: {courses_result['courses']}")
    except Exception as e:
        logger.exception("Failed to reload courses")
        await message.answer(f"\u274c Ошибка загрузки курсов: {e}")
        return

    # Step 4: Sections
    try:
        sections_result = await reload_sections_data(session)
        await message.answer(f"\u2705 Разделы: {sections_result['sections']}")
    except Exception as e:
        logger.exception("Failed to reload sections")
        await message.answer(f"\u274c Ошибка загрузки разделов: {e}")
        return

    # Step 5: Topics
    try:
        topics_result = await reload_topics_data(session)
        await message.answer(f"\u2705 Темы: {topics_result['topics']}")
    except Exception as e:
        logger.exception("Failed to reload topics")
        await message.answer(f"\u274c Ошибка загрузки тем: {e}")
        return

    # Step 6: Lessons
    try:
        lessons_result = await reload_lessons_data(session)
        emb_status = "\u2705" if lessons_result["embeddings"] else "\u26a0\ufe0f без эмбеддингов"
        await message.answer(
            f"\u2705 Уроки: {lessons_result['loaded']} загружено, "
            f"{lessons_result['errors']} ошибок\n"
            f"Эмбеддинги: {emb_status}"
        )
        if lessons_result["error_rows"]:
            await message.answer(f"Строки с ошибками: {lessons_result['error_rows'][:20]}")
    except Exception as e:
        logger.exception("Failed to reload lessons")
        await message.answer(f"\u274c Ошибка загрузки уроков: {e}")
        return

    # Step 7: Lesson links
    try:
        links_result = await reload_lesson_links_data(session)
        await message.answer(f"\u2705 Ссылки: {links_result['links']}")
    except Exception as e:
        logger.exception("Failed to reload lesson links")
        await message.answer(f"\u274c Ошибка загрузки ссылок: {e}")


@router.message(Command("stats"))
async def cmd_stats(message: Message, session):
    if not is_admin(message.from_user.id):
        return

    user_count = await user_service.get_user_count(session)
    await message.answer(f"\U0001f4ca Статистика:\n\nПользователей: {user_count}")
```

**Step 2: Commit**

```bash
git add src/telegram/handlers/admin.py
git commit -m "feat: update admin reload to load all 7 entity types in order"
```

---

### Task 5: Update Search Service and Schemas

**Files:**
- Modify: `src/core/schemas.py`
- Modify: `src/core/services/search.py`

**Step 1: Update schemas**

In `src/core/schemas.py`, update `LessonResult` to remove `lesson_type`, and update `FilterState`:

```python
class LessonResult(BaseModel):
    title: str
    url: str
    description: str | None = None
    subject: str | None = None
    section: str | None = None
    topic: str | None = None
    is_semantic: bool = False


class FilterState(BaseModel):
    subject_id: int | None = None
    grade: int | None = None
    course_id: int | None = None
    section_id: int | None = None
    topic_id: int | None = None
```

**Step 2: Update search service**

In `src/core/services/search.py`, update `LessonResult` construction to join Section/Topic for display names:

- In `fts_search`: join Section and Topic, use `l.section.name` / `l.topic.name`
- In `semantic_search`: same joins
- Remove references to `lesson.lesson_type`

```python
# In fts_search, update the query to eagerly load relationships:
from sqlalchemy.orm import joinedload

q = (
    select(Lesson).join(Subject)
    .options(joinedload(Lesson.section), joinedload(Lesson.topic))
    .where(Lesson.search_vector.op("@@")(ts_query))
    .order_by(func.ts_rank(Lesson.search_vector, ts_query).desc())
    .offset(offset).limit(self.per_page)
)

# Update LessonResult construction:
LessonResult(
    title=l.title, url=l.url,
    description=l.description,
    subject=l.subject.name,
    section=l.section.name if l.section else None,
    topic=l.topic.name if l.topic else None,
    is_semantic=False,
)
```

Apply the same pattern to `semantic_search`.

**Step 3: Check for other files referencing `lesson_type`**

Run: `grep -r "lesson_type" src/` and update any remaining references.

**Step 4: Commit**

```bash
git add src/core/schemas.py src/core/services/search.py
git commit -m "refactor: update search service and schemas for normalized lesson model"
```

---

### Task 6: Update Remaining References

**Files:**
- Modify: `src/core/services/content.py` (if references old lesson fields)
- Modify: `src/telegram/formatters.py` (if references lesson_type)
- Modify: any handler files referencing old fields

**Step 1: Search for all references to old fields**

Run:
```bash
grep -rn "lesson_type\|\.section\b\|\.topic\b" src/ --include="*.py"
```

Update all remaining references to use the new relationships.

**Step 2: Commit**

```bash
git add -u src/
git commit -m "refactor: update all remaining references to old lesson fields"
```

---

### Task 7: Verify Everything Works

**Step 1: Run import check**

Run: `python -c "from src.core.models import *; from src.core.services.loader import *; from src.core.services.search import *; print('All imports OK')"`

**Step 2: Run existing tests**

Run: `pytest tests/ -v`

Fix any failures caused by schema changes.

**Step 3: Commit any test fixes**

```bash
git add tests/
git commit -m "fix: update tests for normalized schema"
```
