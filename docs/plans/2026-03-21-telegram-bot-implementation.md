# Telegram-бот для учителей — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Telegram bot that helps teachers find educational content from a PostgreSQL database (sourced from Google Sheets) using parametric filtering and hybrid FTS+semantic search.

**Architecture:** Core engine (services + models) decoupled from messenger adapters. Telegram adapter translates bot events into core service calls. Data loaded from Google Sheets into PostgreSQL (Supabase) with pgvector for embeddings.

**Tech Stack:** Python 3.12, aiogram 3, SQLAlchemy 2 + asyncpg, Alembic, gspread, openai, pydantic, Docker, PostgreSQL (Supabase + pgvector)

**Design doc:** `docs/plans/2026-03-21-telegram-bot-design.md`

---

## Task 1: Project Scaffold & Configuration

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `src/__init__.py`
- Create: `src/config.py`
- Create: `src/main.py`
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.gitignore`
- Create: `tests/__init__.py`

**Step 1: Initialize git and create .gitignore**

```bash
cd C:/Users/aleks/Documents/Projects/bot_aitsok
git init
```

```gitignore
# .gitignore
__pycache__/
*.pyc
.env
.venv/
venv/
*.egg-info/
dist/
build/
.pytest_cache/
alembic/versions/*.py
!alembic/versions/__init__.py
```

**Step 2: Create requirements.txt**

```txt
aiogram==3.15.0
sqlalchemy[asyncio]==2.0.36
asyncpg==0.30.0
alembic==1.14.1
gspread==6.1.4
google-auth==2.37.0
openai==1.59.0
pydantic==2.10.4
pydantic-settings==2.7.1
pgvector==0.3.6
pytest==8.3.4
pytest-asyncio==0.25.0
```

**Step 3: Create .env.example**

```env
# Telegram
BOT_TOKEN=your-telegram-bot-token
ADMIN_IDS=123456789,987654321

# Database (Supabase)
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/dbname

# Google Sheets
GOOGLE_SHEETS_LESSONS_ID=your-spreadsheet-id
GOOGLE_SHEETS_SCHOOLS_ID=your-spreadsheet-id
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account",...}

# OpenAI
OPENAI_API_KEY=sk-your-key

# Search
FTS_MIN_RESULTS=3
SEMANTIC_SIMILARITY_THRESHOLD=0.75
RESULTS_PER_PAGE=5
```

**Step 4: Create src/config.py**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bot_token: str
    admin_ids: list[int] = []
    database_url: str
    google_sheets_lessons_id: str
    google_sheets_schools_id: str
    google_service_account_json: str
    openai_api_key: str
    fts_min_results: int = 3
    semantic_similarity_threshold: float = 0.75
    results_per_page: int = 5

    class Config:
        env_file = ".env"

    @property
    def sync_database_url(self) -> str:
        return self.database_url.replace("+asyncpg", "")


settings = Settings()
```

**Step 5: Create src/main.py (minimal, just prints config loads)**

```python
import asyncio
import logging

from src.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Bot starting...")
    logger.info("Admin IDs: %s", settings.admin_ids)
    # Will be filled in later tasks


if __name__ == "__main__":
    asyncio.run(main())
```

**Step 6: Create src/__init__.py and tests/__init__.py**

Both empty files.

**Step 7: Create Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "src.main"]
```

**Step 8: Create docker-compose.yml**

```yaml
services:
  bot:
    build: .
    env_file: .env
    restart: unless-stopped
    depends_on:
      - db

  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: bot
      POSTGRES_PASSWORD: bot
      POSTGRES_DB: bot_aitsok
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

**Step 9: Commit**

```bash
git add .gitignore requirements.txt .env.example Dockerfile docker-compose.yml src/__init__.py src/config.py src/main.py tests/__init__.py
git commit -m "feat: project scaffold with config, Docker, and dependencies"
```

---

## Task 2: Database Models & Migrations

**Files:**
- Create: `src/core/__init__.py`
- Create: `src/core/database.py`
- Create: `src/core/models.py`
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/versions/__init__.py`
- Create: `tests/test_models.py`

**Step 1: Write test for models**

```python
# tests/test_models.py
from src.core.models import User, Region, School, Subject, Lesson


def test_user_model_has_required_fields():
    assert hasattr(User, "telegram_id")
    assert hasattr(User, "full_name")
    assert hasattr(User, "phone")
    assert hasattr(User, "email")
    assert hasattr(User, "region_id")
    assert hasattr(User, "school_id")
    assert hasattr(User, "subjects")


def test_lesson_model_has_required_fields():
    assert hasattr(Lesson, "subject_id")
    assert hasattr(Lesson, "grade")
    assert hasattr(Lesson, "section")
    assert hasattr(Lesson, "topic")
    assert hasattr(Lesson, "title")
    assert hasattr(Lesson, "lesson_type")
    assert hasattr(Lesson, "url")
    assert hasattr(Lesson, "search_vector")
    assert hasattr(Lesson, "embedding")


def test_region_model():
    assert hasattr(Region, "name")


def test_school_model():
    assert hasattr(School, "region_id")
    assert hasattr(School, "name")


def test_subject_model():
    assert hasattr(Subject, "name")
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_models.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.core'`

**Step 3: Create src/core/database.py**

```python
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
```

**Step 4: Create src/core/models.py**

```python
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
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

    schools: Mapped[list["School"]] = relationship(back_populates="region")


class School(Base):
    __tablename__ = "schools"
    __table_args__ = (UniqueConstraint("region_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    region: Mapped["Region"] = relationship(back_populates="schools")


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"), nullable=False)
    subjects: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger), default=[])
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    region: Mapped["Region"] = relationship()
    school: Mapped["School"] = relationship()


class Lesson(Base):
    __tablename__ = "lessons"
    __table_args__ = (
        Index("ix_lessons_subject_grade", "subject_id", "grade"),
        Index("ix_lessons_search_vector", "search_vector", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), nullable=False)
    grade: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    section: Mapped[str | None] = mapped_column(String(255), nullable=True)
    topic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    lesson_type: Mapped[str] = mapped_column(String(50), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)
    embedding = mapped_column(Vector(1536), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    subject: Mapped["Subject"] = relationship()
```

**Step 5: Create src/core/__init__.py**

Empty file.

**Step 6: Run tests to verify they pass**

```bash
pytest tests/test_models.py -v
```

Expected: All PASS

**Step 7: Set up Alembic**

```bash
alembic init alembic
```

Then edit `alembic/env.py` — replace the target_metadata line:

```python
# alembic/env.py — key changes:
# Add at top:
from src.core.database import Base
from src.core.models import Region, School, Subject, User, Lesson  # noqa: F401

# Set:
target_metadata = Base.metadata

# In run_migrations_online(), use:
from src.config import settings
connectable = create_engine(settings.sync_database_url)
```

Edit `alembic.ini` — remove the default `sqlalchemy.url` line (we use config.py).

**Step 8: Generate initial migration**

```bash
alembic revision --autogenerate -m "initial schema"
```

**Step 9: Add search_vector trigger migration**

Create a manual migration after the auto-generated one:

```bash
alembic revision -m "add search_vector trigger"
```

In the generated file:

```python
def upgrade():
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
```

**Step 10: Also enable pgvector extension in a migration**

Add to the initial migration's `upgrade()`, before table creation:

```python
op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
```

**Step 11: Run migrations against local DB**

```bash
docker-compose up -d db
alembic upgrade head
```

**Step 12: Commit**

```bash
git add src/core/ alembic/ alembic.ini tests/test_models.py
git commit -m "feat: database models, migrations, search_vector trigger, pgvector"
```

---

## Task 3: Pydantic Schemas (DTOs)

**Files:**
- Create: `src/core/schemas.py`
- Create: `tests/test_schemas.py`

**Step 1: Write tests**

```python
# tests/test_schemas.py
import pytest
from pydantic import ValidationError

from src.core.schemas import (
    LessonResult,
    SearchResult,
    UserCreate,
)


def test_user_create_valid():
    user = UserCreate(
        telegram_id=123456,
        full_name="Иван Петров",
        phone="+79001234567",
        region_id=1,
        school_id=1,
        subjects=[1, 2],
    )
    assert user.full_name == "Иван Петров"


def test_user_create_name_too_short():
    with pytest.raises(ValidationError):
        UserCreate(
            telegram_id=123,
            full_name="Иван",
            phone="+79001234567",
            region_id=1,
            school_id=1,
        )


def test_lesson_result():
    lesson = LessonResult(
        title="Фотосинтез",
        lesson_type="Теория",
        url="https://gosuslugi.ru/123",
        subject="Биология",
        section="Растения",
        topic="Питание растений",
        is_semantic=False,
    )
    assert lesson.title == "Фотосинтез"
    assert lesson.is_semantic is False


def test_search_result_pagination():
    result = SearchResult(
        query="Никон",
        lessons=[],
        total=0,
        page=1,
        per_page=5,
    )
    assert result.total_pages == 0
```

**Step 2: Run tests — expected FAIL**

```bash
pytest tests/test_schemas.py -v
```

**Step 3: Implement schemas**

```python
# src/core/schemas.py
import math

from pydantic import BaseModel, field_validator


class UserCreate(BaseModel):
    telegram_id: int | None = None
    full_name: str
    phone: str
    email: str | None = None
    region_id: int
    school_id: int
    subjects: list[int] = []

    @field_validator("full_name")
    @classmethod
    def name_must_have_two_words(cls, v: str) -> str:
        if len(v.strip().split()) < 2:
            raise ValueError("Введите имя и фамилию (минимум 2 слова)")
        return v.strip()


class LessonResult(BaseModel):
    title: str
    lesson_type: str
    url: str
    subject: str | None = None
    section: str | None = None
    topic: str | None = None
    is_semantic: bool = False


class SearchResult(BaseModel):
    query: str
    lessons: list[LessonResult]
    total: int
    page: int
    per_page: int

    @property
    def total_pages(self) -> int:
        return math.ceil(self.total / self.per_page) if self.total > 0 else 0


class FilterState(BaseModel):
    subject_id: int | None = None
    grade: int | None = None
    section: str | None = None
    topic: str | None = None
```

**Step 4: Run tests — expected PASS**

```bash
pytest tests/test_schemas.py -v
```

**Step 5: Commit**

```bash
git add src/core/schemas.py tests/test_schemas.py
git commit -m "feat: pydantic schemas for user, lesson, search results"
```

---

## Task 4: Google Sheets Loader Service

**Files:**
- Create: `src/core/services/__init__.py`
- Create: `src/core/services/loader.py`
- Create: `tests/test_loader.py`

**Step 1: Write tests**

```python
# tests/test_loader.py
import pytest

from src.core.services.loader import (
    parse_lessons_rows,
    parse_regions_schools_rows,
    validate_lesson_row,
)


def test_validate_lesson_row_valid():
    row = {
        "Предмет": "Математика",
        "Класс": "5",
        "Раздел": "Алгебра",
        "Тема": "Линейные уравнения",
        "Урок": "Что такое уравнение",
        "Вид": "Теория",
        "Ссылка": "https://gosuslugi.ru/123",
    }
    result = validate_lesson_row(row, row_num=2)
    assert result is not None
    assert result["subject"] == "Математика"
    assert result["grade"] == 5


def test_validate_lesson_row_missing_url():
    row = {
        "Предмет": "Математика",
        "Класс": "5",
        "Раздел": "",
        "Тема": "",
        "Урок": "Тест",
        "Вид": "Теория",
        "Ссылка": "",
    }
    result = validate_lesson_row(row, row_num=2)
    assert result is None


def test_validate_lesson_row_missing_subject():
    row = {
        "Предмет": "",
        "Класс": "5",
        "Раздел": "",
        "Тема": "",
        "Урок": "Тест",
        "Вид": "Теория",
        "Ссылка": "https://gosuslugi.ru/123",
    }
    result = validate_lesson_row(row, row_num=2)
    assert result is None


def test_parse_lessons_rows():
    rows = [
        {
            "Предмет": "Математика",
            "Класс": "5",
            "Раздел": "Алгебра",
            "Тема": "Уравнения",
            "Урок": "Линейные уравнения",
            "Вид": "Теория",
            "Ссылка": "https://gosuslugi.ru/1",
        },
        {
            "Предмет": "",
            "Класс": "",
            "Раздел": "",
            "Тема": "",
            "Урок": "",
            "Вид": "",
            "Ссылка": "",
        },
    ]
    lessons, errors = parse_lessons_rows(rows)
    assert len(lessons) == 1
    assert len(errors) == 1


def test_parse_regions_schools_rows():
    rows = [
        {"Регион": "Москва", "Школа": "Школа №1"},
        {"Регион": "Москва", "Школа": "Школа №2"},
        {"Регион": "Санкт-Петербург", "Школа": "Гимназия №1"},
    ]
    regions, schools = parse_regions_schools_rows(rows)
    assert len(regions) == 2
    assert "Москва" in regions
    assert len(schools) == 3
```

**Step 2: Run tests — expected FAIL**

```bash
pytest tests/test_loader.py -v
```

**Step 3: Implement loader (parsing functions)**

```python
# src/core/services/loader.py
import json
import logging

import gspread
from google.oauth2.service_account import Credentials
from openai import AsyncOpenAI
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.models import Lesson, Region, School, Subject

logger = logging.getLogger(__name__)

REQUIRED_LESSON_FIELDS = ["Предмет", "Класс", "Урок", "Вид", "Ссылка"]


def validate_lesson_row(row: dict, row_num: int) -> dict | None:
    for field in REQUIRED_LESSON_FIELDS:
        if not row.get(field, "").strip():
            logger.warning("Row %d: missing required field '%s'", row_num, field)
            return None
    try:
        grade = int(row["Класс"].strip())
    except ValueError:
        logger.warning("Row %d: invalid grade '%s'", row_num, row["Класс"])
        return None
    return {
        "subject": row["Предмет"].strip(),
        "grade": grade,
        "section": row.get("Раздел", "").strip() or None,
        "topic": row.get("Тема", "").strip() or None,
        "title": row["Урок"].strip(),
        "lesson_type": row["Вид"].strip(),
        "url": row["Ссылка"].strip(),
    }


def parse_lessons_rows(rows: list[dict]) -> tuple[list[dict], list[int]]:
    lessons = []
    errors = []
    for i, row in enumerate(rows, start=2):
        parsed = validate_lesson_row(row, row_num=i)
        if parsed:
            lessons.append(parsed)
        else:
            errors.append(i)
    return lessons, errors


def parse_regions_schools_rows(rows: list[dict]) -> tuple[set[str], list[dict]]:
    regions = set()
    schools = []
    for row in rows:
        region = row.get("Регион", "").strip()
        school = row.get("Школа", "").strip()
        if region and school:
            regions.add(region)
            schools.append({"region": region, "school": school})
    return regions, schools


def _get_gspread_client() -> gspread.Client:
    creds_dict = json.loads(settings.google_service_account_json)
    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    return gspread.authorize(creds)


def fetch_lessons_from_sheets() -> list[dict]:
    client = _get_gspread_client()
    sheet = client.open_by_key(settings.google_sheets_lessons_id).sheet1
    return sheet.get_all_records()


def fetch_schools_from_sheets() -> list[dict]:
    client = _get_gspread_client()
    sheet = client.open_by_key(settings.google_sheets_schools_id).sheet1
    return sheet.get_all_records()


async def generate_embeddings(texts: list[str]) -> list[list[float]]:
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


async def reload_schools_data(session: AsyncSession) -> dict:
    rows = fetch_schools_from_sheets()
    regions_set, schools_list = parse_regions_schools_rows(rows)

    # Upsert regions
    for name in regions_set:
        stmt = pg_insert(Region).values(name=name).on_conflict_do_nothing(index_elements=["name"])
        await session.execute(stmt)
    await session.flush()

    # Get region id map
    result = await session.execute(select(Region))
    region_map = {r.name: r.id for r in result.scalars().all()}

    # Upsert schools
    for item in schools_list:
        region_id = region_map.get(item["region"])
        if region_id:
            stmt = (
                pg_insert(School)
                .values(region_id=region_id, name=item["school"])
                .on_conflict_do_nothing(constraint="uq_schools_region_id_name")
            )
            await session.execute(stmt)

    await session.commit()
    return {"regions": len(regions_set), "schools": len(schools_list)}


async def reload_lessons_data(session: AsyncSession) -> dict:
    rows = fetch_lessons_from_sheets()
    lessons, errors = parse_lessons_rows(rows)

    # Collect unique subjects
    subject_names = {lesson["subject"] for lesson in lessons}
    for name in subject_names:
        stmt = pg_insert(Subject).values(name=name).on_conflict_do_nothing(index_elements=["name"])
        await session.execute(stmt)
    await session.flush()

    # Get subject id map
    result = await session.execute(select(Subject))
    subject_map = {s.name: s.id for s in result.scalars().all()}

    # Delete old lessons and insert new
    await session.execute(delete(Lesson))

    # Generate embeddings
    texts = [
        " ".join(filter(None, [l["title"], l["section"], l["topic"]]))
        for l in lessons
    ]
    try:
        embeddings = await generate_embeddings(texts)
    except Exception:
        logger.exception("Failed to generate embeddings")
        embeddings = [None] * len(lessons)

    for i, lesson in enumerate(lessons):
        db_lesson = Lesson(
            subject_id=subject_map[lesson["subject"]],
            grade=lesson["grade"],
            section=lesson["section"],
            topic=lesson["topic"],
            title=lesson["title"],
            lesson_type=lesson["lesson_type"],
            url=lesson["url"],
            embedding=embeddings[i],
        )
        session.add(db_lesson)

    await session.commit()
    return {
        "loaded": len(lessons),
        "errors": len(errors),
        "error_rows": errors,
        "embeddings": embeddings[0] is not None if embeddings else False,
    }
```

**Step 4: Run tests — expected PASS**

```bash
pytest tests/test_loader.py -v
```

**Step 5: Commit**

```bash
git add src/core/services/ tests/test_loader.py
git commit -m "feat: Google Sheets loader with validation and embeddings generation"
```

---

## Task 5: Content Service (Path A Filtering)

**Files:**
- Create: `src/core/services/content.py`
- Create: `tests/test_content.py`

**Step 1: Write tests**

```python
# tests/test_content.py
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.services.content import ContentService


@pytest.fixture
def content_service():
    return ContentService()


def test_content_service_has_required_methods(content_service):
    assert hasattr(content_service, "get_subjects")
    assert hasattr(content_service, "get_grades_for_subject")
    assert hasattr(content_service, "get_sections")
    assert hasattr(content_service, "get_topics")
    assert hasattr(content_service, "get_lessons")
```

**Step 2: Run tests — expected FAIL**

```bash
pytest tests/test_content.py -v
```

**Step 3: Implement content service**

```python
# src/core/services/content.py
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import Lesson, Subject
from src.core.schemas import FilterState, LessonResult


class ContentService:
    async def get_subjects(self, session: AsyncSession) -> list[dict]:
        result = await session.execute(
            select(Subject).order_by(Subject.name)
        )
        return [{"id": s.id, "name": s.name} for s in result.scalars().all()]

    async def get_grades_for_subject(
        self, session: AsyncSession, subject_id: int
    ) -> list[int]:
        result = await session.execute(
            select(distinct(Lesson.grade))
            .where(Lesson.subject_id == subject_id)
            .order_by(Lesson.grade)
        )
        return list(result.scalars().all())

    async def get_sections(
        self, session: AsyncSession, subject_id: int, grade: int
    ) -> list[str]:
        result = await session.execute(
            select(distinct(Lesson.section))
            .where(Lesson.subject_id == subject_id, Lesson.grade == grade)
            .where(Lesson.section.is_not(None))
            .order_by(Lesson.section)
        )
        return list(result.scalars().all())

    async def get_topics(
        self, session: AsyncSession, subject_id: int, grade: int, section: str
    ) -> list[str]:
        result = await session.execute(
            select(distinct(Lesson.topic))
            .where(
                Lesson.subject_id == subject_id,
                Lesson.grade == grade,
                Lesson.section == section,
            )
            .where(Lesson.topic.is_not(None))
            .order_by(Lesson.topic)
        )
        return list(result.scalars().all())

    async def get_lessons(
        self,
        session: AsyncSession,
        filters: FilterState,
        page: int = 1,
        per_page: int = 5,
    ) -> tuple[list[LessonResult], int]:
        query = select(Lesson).join(Subject)
        count_query = select(Lesson.id).join(Subject)

        if filters.subject_id:
            query = query.where(Lesson.subject_id == filters.subject_id)
            count_query = count_query.where(Lesson.subject_id == filters.subject_id)
        if filters.grade:
            query = query.where(Lesson.grade == filters.grade)
            count_query = count_query.where(Lesson.grade == filters.grade)
        if filters.section:
            query = query.where(Lesson.section == filters.section)
            count_query = count_query.where(Lesson.section == filters.section)
        if filters.topic:
            query = query.where(Lesson.topic == filters.topic)
            count_query = count_query.where(Lesson.topic == filters.topic)

        # Count
        count_result = await session.execute(count_query)
        total = len(count_result.all())

        # Paginate
        offset = (page - 1) * per_page
        query = query.order_by(Lesson.title).offset(offset).limit(per_page)
        result = await session.execute(query)

        lessons = [
            LessonResult(
                title=l.title,
                lesson_type=l.lesson_type,
                url=l.url,
                subject=l.subject.name,
                section=l.section,
                topic=l.topic,
            )
            for l in result.scalars().all()
        ]
        return lessons, total
```

**Step 4: Run tests — expected PASS**

```bash
pytest tests/test_content.py -v
```

**Step 5: Commit**

```bash
git add src/core/services/content.py tests/test_content.py
git commit -m "feat: content service with parametric filtering and pagination"
```

---

## Task 6: Search Service (FTS + Semantic)

**Files:**
- Create: `src/core/services/search.py`
- Create: `tests/test_search.py`

**Step 1: Write tests**

```python
# tests/test_search.py
from src.core.services.search import SearchService


def test_search_service_has_required_methods():
    service = SearchService()
    assert hasattr(service, "fts_search")
    assert hasattr(service, "semantic_search")
    assert hasattr(service, "hybrid_search")


def test_search_service_default_config():
    service = SearchService()
    assert service.fts_min_results == 3
    assert service.similarity_threshold == 0.75
```

**Step 2: Run tests — expected FAIL**

```bash
pytest tests/test_search.py -v
```

**Step 3: Implement search service**

```python
# src/core/services/search.py
import logging

from openai import AsyncOpenAI
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.models import Lesson, Subject
from src.core.schemas import LessonResult, SearchResult

logger = logging.getLogger(__name__)


class SearchService:
    def __init__(self):
        self.fts_min_results = settings.fts_min_results
        self.similarity_threshold = settings.semantic_similarity_threshold
        self.per_page = settings.results_per_page

    async def fts_search(
        self, session: AsyncSession, query: str, page: int = 1
    ) -> tuple[list[LessonResult], int]:
        ts_query = func.plainto_tsquery("russian", query)

        count_q = (
            select(func.count(Lesson.id))
            .where(Lesson.search_vector.op("@@")(ts_query))
        )
        count_result = await session.execute(count_q)
        total = count_result.scalar() or 0

        offset = (page - 1) * self.per_page
        q = (
            select(Lesson)
            .join(Subject)
            .where(Lesson.search_vector.op("@@")(ts_query))
            .order_by(func.ts_rank(Lesson.search_vector, ts_query).desc())
            .offset(offset)
            .limit(self.per_page)
        )
        result = await session.execute(q)

        lessons = [
            LessonResult(
                title=l.title,
                lesson_type=l.lesson_type,
                url=l.url,
                subject=l.subject.name,
                section=l.section,
                topic=l.topic,
                is_semantic=False,
            )
            for l in result.scalars().all()
        ]
        return lessons, total

    async def semantic_search(
        self, session: AsyncSession, query: str, exclude_ids: list[int] | None = None, limit: int = 10
    ) -> list[LessonResult]:
        try:
            client = AsyncOpenAI(api_key=settings.openai_api_key)
            response = await client.embeddings.create(
                model="text-embedding-3-small",
                input=query,
            )
            query_embedding = response.data[0].embedding
        except Exception:
            logger.exception("Failed to generate query embedding")
            return []

        q = (
            select(
                Lesson,
                Lesson.embedding.cosine_distance(query_embedding).label("distance"),
            )
            .join(Subject)
            .where(Lesson.embedding.is_not(None))
        )
        if exclude_ids:
            q = q.where(Lesson.id.notin_(exclude_ids))

        q = q.order_by("distance").limit(limit)
        result = await session.execute(q)

        lessons = []
        for row in result.all():
            lesson = row[0]
            distance = row[1]
            similarity = 1 - distance
            if similarity >= self.similarity_threshold:
                lessons.append(
                    LessonResult(
                        title=lesson.title,
                        lesson_type=lesson.lesson_type,
                        url=lesson.url,
                        subject=lesson.subject.name,
                        section=lesson.section,
                        topic=lesson.topic,
                        is_semantic=True,
                    )
                )
        return lessons

    async def hybrid_search(
        self, session: AsyncSession, query: str, page: int = 1
    ) -> SearchResult:
        # Step 1: FTS
        fts_lessons, fts_total = await self.fts_search(session, query, page=1)

        if fts_total >= self.fts_min_results:
            # Enough FTS results — paginate normally
            if page > 1:
                fts_lessons, _ = await self.fts_search(session, query, page=page)
            return SearchResult(
                query=query,
                lessons=fts_lessons,
                total=fts_total,
                page=page,
                per_page=self.per_page,
            )

        # Step 2: Not enough FTS results — add semantic
        fts_all, _ = await self.fts_search(session, query, page=1)
        # Get IDs of FTS results to exclude from semantic
        fts_id_query = (
            select(Lesson.id)
            .where(Lesson.search_vector.op("@@")(func.plainto_tsquery("russian", query)))
        )
        fts_id_result = await session.execute(fts_id_query)
        exclude_ids = [row[0] for row in fts_id_result.all()]

        semantic_lessons = await self.semantic_search(
            session, query, exclude_ids=exclude_ids
        )

        combined = fts_all + semantic_lessons
        total = len(combined)

        # Paginate combined
        offset = (page - 1) * self.per_page
        page_lessons = combined[offset : offset + self.per_page]

        return SearchResult(
            query=query,
            lessons=page_lessons,
            total=total,
            page=page,
            per_page=self.per_page,
        )
```

**Step 4: Run tests — expected PASS**

```bash
pytest tests/test_search.py -v
```

**Step 5: Commit**

```bash
git add src/core/services/search.py tests/test_search.py
git commit -m "feat: hybrid search service with FTS and semantic fallback"
```

---

## Task 7: User Service

**Files:**
- Create: `src/core/services/user.py`
- Create: `tests/test_user.py`

**Step 1: Write tests**

```python
# tests/test_user.py
from src.core.services.user import UserService


def test_user_service_has_required_methods():
    service = UserService()
    assert hasattr(service, "get_by_telegram_id")
    assert hasattr(service, "create_user")
    assert hasattr(service, "search_regions")
    assert hasattr(service, "search_schools")
    assert hasattr(service, "get_user_count")
```

**Step 2: Run tests — expected FAIL**

```bash
pytest tests/test_user.py -v
```

**Step 3: Implement user service**

```python
# src/core/services/user.py
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import Region, School, Subject, User
from src.core.schemas import UserCreate


class UserService:
    async def get_by_telegram_id(
        self, session: AsyncSession, telegram_id: int
    ) -> User | None:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def create_user(self, session: AsyncSession, data: UserCreate) -> User:
        user = User(
            telegram_id=data.telegram_id,
            full_name=data.full_name,
            phone=data.phone,
            email=data.email,
            region_id=data.region_id,
            school_id=data.school_id,
            subjects=data.subjects,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    async def search_regions(
        self, session: AsyncSession, query: str, limit: int = 8
    ) -> list[dict]:
        result = await session.execute(
            select(Region)
            .where(Region.name.ilike(f"%{query}%"))
            .order_by(Region.name)
            .limit(limit)
        )
        return [{"id": r.id, "name": r.name} for r in result.scalars().all()]

    async def search_schools(
        self, session: AsyncSession, region_id: int, query: str, limit: int = 8
    ) -> list[dict]:
        result = await session.execute(
            select(School)
            .where(School.region_id == region_id, School.name.ilike(f"%{query}%"))
            .order_by(School.name)
            .limit(limit)
        )
        return [{"id": s.id, "name": s.name} for s in result.scalars().all()]

    async def get_all_subjects(self, session: AsyncSession) -> list[dict]:
        result = await session.execute(select(Subject).order_by(Subject.name))
        return [{"id": s.id, "name": s.name} for s in result.scalars().all()]

    async def get_user_count(self, session: AsyncSession) -> int:
        result = await session.execute(select(func.count(User.id)))
        return result.scalar() or 0
```

**Step 4: Run tests — expected PASS**

```bash
pytest tests/test_user.py -v
```

**Step 5: Commit**

```bash
git add src/core/services/user.py tests/test_user.py
git commit -m "feat: user service with registration and region/school search"
```

---

## Task 8: Telegram Bot Setup & Middlewares

**Files:**
- Create: `src/telegram/__init__.py`
- Create: `src/telegram/bot.py`
- Create: `src/telegram/middlewares.py`
- Create: `src/telegram/handlers/__init__.py`

**Step 1: Create src/telegram/bot.py**

```python
# src/telegram/bot.py
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from src.config import settings

bot = Bot(token=settings.bot_token)
dp = Dispatcher(storage=MemoryStorage())
```

**Step 2: Create src/telegram/middlewares.py**

```python
# src/telegram/middlewares.py
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from src.core.database import async_session


class DatabaseMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with async_session() as session:
            data["session"] = session
            return await handler(event, data)
```

**Step 3: Create src/telegram/handlers/__init__.py**

```python
# src/telegram/handlers/__init__.py
from aiogram import Router

from src.telegram.handlers.admin import router as admin_router
from src.telegram.handlers.menu import router as menu_router
from src.telegram.handlers.param_search import router as param_search_router
from src.telegram.handlers.start import router as start_router
from src.telegram.handlers.text_search import router as text_search_router


def register_all_routers(parent_router: Router) -> None:
    parent_router.include_router(start_router)
    parent_router.include_router(admin_router)
    parent_router.include_router(menu_router)
    parent_router.include_router(param_search_router)
    parent_router.include_router(text_search_router)
```

**Step 4: Create empty handler files (stubs)**

Create these files with minimal router setup:

```python
# src/telegram/handlers/start.py
from aiogram import Router
router = Router()

# src/telegram/handlers/menu.py
from aiogram import Router
router = Router()

# src/telegram/handlers/param_search.py
from aiogram import Router
router = Router()

# src/telegram/handlers/text_search.py
from aiogram import Router
router = Router()

# src/telegram/handlers/admin.py
from aiogram import Router
router = Router()
```

**Step 5: Update src/main.py**

```python
# src/main.py
import asyncio
import logging

from src.config import settings
from src.telegram.bot import bot, dp
from src.telegram.handlers import register_all_routers
from src.telegram.middlewares import DatabaseMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Bot starting...")

    dp.update.middleware(DatabaseMiddleware())
    register_all_routers(dp)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
```

**Step 6: Create src/telegram/__init__.py**

Empty file.

**Step 7: Commit**

```bash
git add src/telegram/ src/main.py
git commit -m "feat: telegram bot setup with dispatcher, middleware, router stubs"
```

---

## Task 9: Keyboards & Formatters

**Files:**
- Create: `src/telegram/keyboards.py`
- Create: `src/telegram/formatters.py`

**Step 1: Create keyboards.py**

```python
# src/telegram/keyboards.py
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Поиск по параметрам", callback_data="search_params")],
        [InlineKeyboardButton(text="💬 Поиск по словам", callback_data="search_text")],
    ])


def items_keyboard(
    items: list[dict], callback_prefix: str, add_skip: bool = False
) -> InlineKeyboardMarkup:
    buttons = []
    for item in items:
        btn_id = item.get("id", item.get("name", ""))
        buttons.append([
            InlineKeyboardButton(
                text=item["name"],
                callback_data=f"{callback_prefix}:{btn_id}",
            )
        ])
    if add_skip:
        buttons.append([
            InlineKeyboardButton(text="⏭ Пропустить", callback_data=f"{callback_prefix}:skip")
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def grades_keyboard(grades: list[int], callback_prefix: str) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for g in grades:
        row.append(InlineKeyboardButton(text=str(g), callback_data=f"{callback_prefix}:{g}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def subjects_toggle_keyboard(
    subjects: list[dict], selected: set[int]
) -> InlineKeyboardMarkup:
    buttons = []
    for s in subjects:
        mark = "✅" if s["id"] in selected else "⬜"
        buttons.append([
            InlineKeyboardButton(
                text=f"{mark} {s['name']}",
                callback_data=f"onb_subj:{s['id']}",
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="✔️ Готово", callback_data="onb_subj:done")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def pagination_keyboard(
    page: int, total_pages: int, callback_prefix: str
) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    if page > 1:
        row.append(InlineKeyboardButton(text="◀ Назад", callback_data=f"{callback_prefix}:page:{page - 1}"))
    row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        row.append(InlineKeyboardButton(text="Далее ▶", callback_data=f"{callback_prefix}:page:{page + 1}"))
    buttons.append(row)
    buttons.append([
        InlineKeyboardButton(text="🔄 Новый поиск", callback_data="new_search")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить контакт", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def skip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="onb_skip")]
    ])
```

**Step 2: Create formatters.py**

```python
# src/telegram/formatters.py
from src.core.schemas import LessonResult, SearchResult


def format_lesson_param(lesson: LessonResult) -> str:
    return (
        f"📚 {lesson.title}\n"
        f"Вид: {lesson.lesson_type}\n"
        f"→ {lesson.url}"
    )


def format_lesson_text(lesson: LessonResult, index: int) -> str:
    semantic_mark = "🤖 " if lesson.is_semantic else ""
    parts = [p for p in [lesson.subject, lesson.section, lesson.topic] if p]
    context = " | ".join(parts)
    return (
        f"{index}. {semantic_mark}{context}\n"
        f"   📚 {lesson.title}\n"
        f"   Вид: {lesson.lesson_type}\n"
        f"   → {lesson.url}"
    )


def format_param_results(lessons: list[LessonResult]) -> str:
    if not lessons:
        return "Ничего не найдено. Попробуйте изменить параметры поиска."
    return "\n\n".join(format_lesson_param(l) for l in lessons)


def format_text_results(result: SearchResult) -> str:
    if not result.lessons:
        return (
            f'🔎 По запросу «{result.query}» ничего не найдено.\n'
            "Попробуйте другие ключевые слова или поиск по параметрам."
        )
    header = f'🔎 По запросу «{result.query}» найдено {result.total} результатов:\n\n'
    start_index = (result.page - 1) * result.per_page + 1
    items = "\n\n".join(
        format_lesson_text(l, start_index + i)
        for i, l in enumerate(result.lessons)
    )
    return header + items
```

**Step 3: Commit**

```bash
git add src/telegram/keyboards.py src/telegram/formatters.py
git commit -m "feat: telegram keyboards and result formatters"
```

---

## Task 10: Onboarding Handler (FSM)

**Files:**
- Modify: `src/telegram/handlers/start.py`

**Step 1: Implement onboarding FSM**

```python
# src/telegram/handlers/start.py
from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, ContentType, Message

from src.core.schemas import UserCreate
from src.core.services.user import UserService
from src.telegram.keyboards import (
    contact_keyboard,
    items_keyboard,
    main_menu_keyboard,
    skip_keyboard,
    subjects_toggle_keyboard,
)

router = Router()
user_service = UserService()


class OnboardingStates(StatesGroup):
    full_name = State()
    region = State()
    school = State()
    subjects = State()
    phone = State()
    email = State()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, session):
    user = await user_service.get_by_telegram_id(session, message.from_user.id)
    if user:
        await state.clear()
        await message.answer(
            f"С возвращением, {user.full_name}! Выберите действие:",
            reply_markup=main_menu_keyboard(),
        )
        return
    await state.set_state(OnboardingStates.full_name)
    await message.answer(
        "Добро пожаловать! Давайте зарегистрируемся.\n\n"
        "Введите ваше имя и фамилию:"
    )


@router.message(OnboardingStates.full_name)
async def process_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name.split()) < 2:
        await message.answer("Пожалуйста, введите имя и фамилию (минимум 2 слова):")
        return
    await state.update_data(full_name=name)
    await state.set_state(OnboardingStates.region)
    await message.answer("Из какого вы региона? Начните вводить название:")


@router.message(OnboardingStates.region, F.text)
async def process_region_search(message: Message, state: FSMContext, session):
    regions = await user_service.search_regions(session, message.text.strip())
    if not regions:
        await message.answer("Регион не найден. Попробуйте ввести другое название:")
        return
    await message.answer(
        "Выберите регион:",
        reply_markup=items_keyboard(regions, "onb_region"),
    )


@router.callback_query(F.data.startswith("onb_region:"))
async def process_region_select(callback: CallbackQuery, state: FSMContext):
    region_id = int(callback.data.split(":")[1])
    await state.update_data(region_id=region_id)
    await state.set_state(OnboardingStates.school)
    await callback.message.edit_text(
        "Введите название или номер школы:"
    )
    await callback.answer()


@router.message(OnboardingStates.school, F.text)
async def process_school_search(message: Message, state: FSMContext, session):
    data = await state.get_data()
    schools = await user_service.search_schools(
        session, data["region_id"], message.text.strip()
    )
    if not schools:
        await message.answer("Школа не найдена. Попробуйте другое название:")
        return
    await message.answer(
        "Выберите школу:",
        reply_markup=items_keyboard(schools, "onb_school"),
    )


@router.callback_query(F.data.startswith("onb_school:"))
async def process_school_select(callback: CallbackQuery, state: FSMContext, session):
    school_id = int(callback.data.split(":")[1])
    await state.update_data(school_id=school_id)
    await state.set_state(OnboardingStates.subjects)
    subjects = await user_service.get_all_subjects(session)
    await state.update_data(available_subjects=subjects, selected_subjects=set())
    await callback.message.edit_text(
        "Какие предметы вы ведёте? Выберите и нажмите «Готово»:",
        reply_markup=subjects_toggle_keyboard(subjects, set()),
    )
    await callback.answer()


@router.callback_query(OnboardingStates.subjects, F.data.startswith("onb_subj:"))
async def process_subject_toggle(callback: CallbackQuery, state: FSMContext):
    value = callback.data.split(":")[1]
    data = await state.get_data()
    selected = set(data.get("selected_subjects", []))
    subjects = data["available_subjects"]

    if value == "done":
        await state.update_data(subjects=list(selected))
        await state.set_state(OnboardingStates.phone)
        await callback.message.edit_text(
            "Поделитесь номером телефона:"
        )
        await callback.message.answer(
            "Нажмите кнопку ниже или введите номер вручную:",
            reply_markup=contact_keyboard(),
        )
        await callback.answer()
        return

    subj_id = int(value)
    if subj_id in selected:
        selected.discard(subj_id)
    else:
        selected.add(subj_id)
    await state.update_data(selected_subjects=selected)
    await callback.message.edit_reply_markup(
        reply_markup=subjects_toggle_keyboard(subjects, selected),
    )
    await callback.answer()


@router.message(OnboardingStates.phone, F.contact)
async def process_phone_contact(message: Message, state: FSMContext):
    await state.update_data(phone=message.contact.phone_number)
    await state.set_state(OnboardingStates.email)
    await message.answer(
        "Введите email (или нажмите «Пропустить»):",
        reply_markup=skip_keyboard(),
    )


@router.message(OnboardingStates.phone, F.text)
async def process_phone_text(message: Message, state: FSMContext):
    phone = message.text.strip()
    if len(phone) < 10:
        await message.answer("Введите корректный номер телефона:")
        return
    await state.update_data(phone=phone)
    await state.set_state(OnboardingStates.email)
    await message.answer(
        "Введите email (или нажмите «Пропустить»):",
        reply_markup=skip_keyboard(),
    )


@router.message(OnboardingStates.email, F.text)
async def process_email(message: Message, state: FSMContext, session):
    await state.update_data(email=message.text.strip())
    await _finish_onboarding(message, state, session)


@router.callback_query(OnboardingStates.email, F.data == "onb_skip")
async def process_email_skip(callback: CallbackQuery, state: FSMContext, session):
    await _finish_onboarding(callback.message, state, session, from_callback=True)
    await callback.answer()


async def _finish_onboarding(message, state: FSMContext, session, from_callback=False):
    data = await state.get_data()
    user_data = UserCreate(
        telegram_id=message.chat.id if not from_callback else message.chat.id,
        full_name=data["full_name"],
        phone=data["phone"],
        email=data.get("email"),
        region_id=data["region_id"],
        school_id=data["school_id"],
        subjects=data.get("subjects", []),
    )
    await user_service.create_user(session, user_data)
    await state.clear()
    await message.answer(
        "✅ Регистрация завершена! Выберите действие:",
        reply_markup=main_menu_keyboard(),
    )
```

**Step 2: Commit**

```bash
git add src/telegram/handlers/start.py
git commit -m "feat: onboarding FSM with name, region, school, subjects, phone, email"
```

---

## Task 11: Menu & Param Search Handler (Path A)

**Files:**
- Modify: `src/telegram/handlers/menu.py`
- Modify: `src/telegram/handlers/param_search.py`

**Step 1: Implement menu handler**

```python
# src/telegram/handlers/menu.py
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from src.telegram.keyboards import main_menu_keyboard

router = Router()


@router.callback_query(F.data == "new_search")
async def new_search(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Выберите действие:",
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()
```

**Step 2: Implement param search handler**

```python
# src/telegram/handlers/param_search.py
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from src.core.schemas import FilterState
from src.core.services.content import ContentService
from src.telegram.formatters import format_param_results
from src.telegram.keyboards import (
    grades_keyboard,
    items_keyboard,
    pagination_keyboard,
)

router = Router()
content_service = ContentService()


@router.callback_query(F.data == "search_params")
async def start_param_search(callback: CallbackQuery, state: FSMContext, session):
    subjects = await content_service.get_subjects(session)
    await state.update_data(filter={})
    await callback.message.edit_text(
        "Выберите предмет:",
        reply_markup=items_keyboard(subjects, "ps_subj"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ps_subj:"))
async def select_subject(callback: CallbackQuery, state: FSMContext, session):
    subject_id = int(callback.data.split(":")[1])
    await state.update_data(filter={"subject_id": subject_id})
    grades = await content_service.get_grades_for_subject(session, subject_id)
    await callback.message.edit_text(
        "Выберите класс:",
        reply_markup=grades_keyboard(grades, "ps_grade"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ps_grade:"))
async def select_grade(callback: CallbackQuery, state: FSMContext, session):
    grade = int(callback.data.split(":")[1])
    data = await state.get_data()
    filters = data["filter"]
    filters["grade"] = grade
    await state.update_data(filter=filters)

    sections = await content_service.get_sections(
        session, filters["subject_id"], grade
    )
    if sections:
        section_items = [{"name": s} for s in sections]
        await callback.message.edit_text(
            "Выберите раздел:",
            reply_markup=items_keyboard(section_items, "ps_section", add_skip=True),
        )
    else:
        await _show_results(callback, state, session)
    await callback.answer()


@router.callback_query(F.data.startswith("ps_section:"))
async def select_section(callback: CallbackQuery, state: FSMContext, session):
    value = callback.data.split(":")[1]
    data = await state.get_data()
    filters = data["filter"]

    if value == "skip":
        await _show_results(callback, state, session)
        await callback.answer()
        return

    filters["section"] = value
    await state.update_data(filter=filters)

    topics = await content_service.get_topics(
        session, filters["subject_id"], filters["grade"], value
    )
    if topics:
        topic_items = [{"name": t} for t in topics]
        await callback.message.edit_text(
            "Выберите тему:",
            reply_markup=items_keyboard(topic_items, "ps_topic", add_skip=True),
        )
    else:
        await _show_results(callback, state, session)
    await callback.answer()


@router.callback_query(F.data.startswith("ps_topic:"))
async def select_topic(callback: CallbackQuery, state: FSMContext, session):
    value = callback.data.split(":")[1]
    data = await state.get_data()
    filters = data["filter"]

    if value != "skip":
        filters["topic"] = value
        await state.update_data(filter=filters)

    await _show_results(callback, state, session)
    await callback.answer()


@router.callback_query(F.data.startswith("ps_results:page:"))
async def paginate_results(callback: CallbackQuery, state: FSMContext, session):
    page = int(callback.data.split(":")[-1])
    await _show_results(callback, state, session, page=page)
    await callback.answer()


async def _show_results(callback, state, session, page=1):
    data = await state.get_data()
    filters = FilterState(**data["filter"])
    lessons, total = await content_service.get_lessons(session, filters, page=page)

    text = format_param_results(lessons)
    total_pages = -(-total // 5)  # ceil division

    keyboard = None
    if total_pages > 0:
        keyboard = pagination_keyboard(page, total_pages, "ps_results")

    await callback.message.edit_text(text, reply_markup=keyboard)
```

**Step 3: Commit**

```bash
git add src/telegram/handlers/menu.py src/telegram/handlers/param_search.py
git commit -m "feat: menu and parametric search handlers with pagination"
```

---

## Task 12: Text Search Handler (Path B)

**Files:**
- Modify: `src/telegram/handlers/text_search.py`

**Step 1: Implement text search handler**

```python
# src/telegram/handlers/text_search.py
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from src.core.services.search import SearchService
from src.telegram.formatters import format_text_results
from src.telegram.keyboards import pagination_keyboard

router = Router()
search_service = SearchService()


class TextSearchStates(StatesGroup):
    waiting_query = State()


@router.callback_query(F.data == "search_text")
async def start_text_search(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TextSearchStates.waiting_query)
    await callback.message.edit_text(
        "Введите ключевое слово или фразу для поиска:"
    )
    await callback.answer()


@router.message(TextSearchStates.waiting_query, F.text)
async def process_text_query(message: Message, state: FSMContext, session):
    query = message.text.strip()
    if len(query) < 2:
        await message.answer("Слишком короткий запрос. Введите минимум 2 символа:")
        return

    await state.update_data(search_query=query)
    await state.set_state(None)

    result = await search_service.hybrid_search(session, query, page=1)
    text = format_text_results(result)

    keyboard = None
    if result.total_pages > 0:
        keyboard = pagination_keyboard(1, result.total_pages, "ts_results")

    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("ts_results:page:"))
async def paginate_text_results(callback: CallbackQuery, state: FSMContext, session):
    page = int(callback.data.split(":")[-1])
    data = await state.get_data()
    query = data.get("search_query", "")

    result = await search_service.hybrid_search(session, query, page=page)
    text = format_text_results(result)
    keyboard = pagination_keyboard(page, result.total_pages, "ts_results")

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()
```

**Step 2: Commit**

```bash
git add src/telegram/handlers/text_search.py
git commit -m "feat: text search handler with hybrid FTS+semantic search"
```

---

## Task 13: Admin Handler

**Files:**
- Modify: `src/telegram/handlers/admin.py`

**Step 1: Implement admin commands**

```python
# src/telegram/handlers/admin.py
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.config import settings
from src.core.services.loader import reload_lessons_data, reload_schools_data
from src.core.services.user import UserService

router = Router()
logger = logging.getLogger(__name__)
user_service = UserService()


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


@router.message(Command("reload"))
async def cmd_reload(message: Message, session):
    if not is_admin(message.from_user.id):
        return

    await message.answer("⏳ Загрузка данных...")

    try:
        schools_result = await reload_schools_data(session)
        await message.answer(
            f"✅ Регионы/школы: {schools_result['regions']} регионов, "
            f"{schools_result['schools']} школ"
        )
    except Exception as e:
        logger.exception("Failed to reload schools")
        await message.answer(f"❌ Ошибка загрузки школ: {e}")

    try:
        lessons_result = await reload_lessons_data(session)
        emb_status = "✅" if lessons_result["embeddings"] else "⚠️ без эмбеддингов"
        await message.answer(
            f"✅ Уроки: {lessons_result['loaded']} загружено, "
            f"{lessons_result['errors']} ошибок\n"
            f"Эмбеддинги: {emb_status}"
        )
        if lessons_result["error_rows"]:
            await message.answer(
                f"Строки с ошибками: {lessons_result['error_rows'][:20]}"
            )
    except Exception as e:
        logger.exception("Failed to reload lessons")
        await message.answer(f"❌ Ошибка загрузки уроков: {e}")


@router.message(Command("stats"))
async def cmd_stats(message: Message, session):
    if not is_admin(message.from_user.id):
        return

    user_count = await user_service.get_user_count(session)
    await message.answer(f"📊 Статистика:\n\nПользователей: {user_count}")
```

**Step 2: Commit**

```bash
git add src/telegram/handlers/admin.py
git commit -m "feat: admin /reload and /stats commands"
```

---

## Task 14: Integration Testing & Final Wiring

**Files:**
- Modify: `src/main.py` (final version)
- Create: `tests/conftest.py`

**Step 1: Create test conftest**

```python
# tests/conftest.py
import pytest


@pytest.fixture
def sample_lessons():
    return [
        {
            "Предмет": "Математика",
            "Класс": "5",
            "Раздел": "Алгебра",
            "Тема": "Уравнения",
            "Урок": "Линейные уравнения",
            "Вид": "Теория",
            "Ссылка": "https://gosuslugi.ru/1",
        },
        {
            "Предмет": "История",
            "Класс": "7",
            "Раздел": "Раскол церкви",
            "Тема": "Реформы",
            "Урок": "Патриарх Никон и его реформы",
            "Вид": "Теория",
            "Ссылка": "https://gosuslugi.ru/2",
        },
    ]
```

**Step 2: Run all tests**

```bash
pytest tests/ -v
```

Expected: All PASS

**Step 3: Manual smoke test**

```bash
# Create .env from .env.example and fill in real values
cp .env.example .env
# Edit .env with real credentials

# Run locally
python -m src.main
```

Test in Telegram:
1. `/start` → onboarding flow
2. Complete registration
3. Main menu → "Поиск по параметрам" → select filters → results
4. Main menu → "Поиск по словам" → enter query → results
5. `/reload` (admin) → data loads
6. `/stats` (admin) → shows count

**Step 4: Commit**

```bash
git add tests/conftest.py
git commit -m "feat: test fixtures and integration test setup"
```

---

## Task 15: Docker & Deployment Config

**Step 1: Verify Dockerfile and docker-compose.yml work**

```bash
docker-compose build
docker-compose up -d db
alembic upgrade head
docker-compose up bot
```

**Step 2: Create Railway-specific Procfile (optional)**

```
# Procfile
worker: python -m src.main
```

**Step 3: Commit**

```bash
git add Procfile
git commit -m "feat: add Procfile for Railway deployment"
```

---

## Summary of Tasks

| # | Task | Dependencies |
|---|------|-------------|
| 1 | Project scaffold & config | None |
| 2 | Database models & migrations | 1 |
| 3 | Pydantic schemas | 1 |
| 4 | Google Sheets loader | 2, 3 |
| 5 | Content service (Path A) | 2, 3 |
| 6 | Search service (FTS + Semantic) | 2, 3 |
| 7 | User service | 2, 3 |
| 8 | Telegram bot setup & middlewares | 1 |
| 9 | Keyboards & formatters | 3 |
| 10 | Onboarding handler | 7, 8, 9 |
| 11 | Menu & param search handler | 5, 8, 9 |
| 12 | Text search handler | 6, 8, 9 |
| 13 | Admin handler | 4, 8 |
| 14 | Integration testing | 10-13 |
| 15 | Docker & deployment | 14 |

**Parallelizable groups:**
- Tasks 3, 4, 5, 6, 7 can run in parallel (all depend on 2)
- Tasks 8, 9 can run in parallel with 4-7
- Tasks 10, 11, 12, 13 can run in parallel (all depend on 8+9)
