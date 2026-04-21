# Search rework (title+description+subject+grade) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the title-only FTS with a weighted FTS over `title + description + subject.name + grade`, strict AND only, no OR fallback, no abbreviation filter.

**Architecture:** Alembic migration `012` redefines the `lessons_search_vector_update()` trigger and backfills. `SearchService.fts_search` is simplified to a single AND-pass. Semantic L2 is untouched. A new integration test locks the behaviour against `examples.csv`.

**Tech Stack:** PostgreSQL FTS (`to_tsvector('russian', ...)`, `plainto_tsquery`, `setweight`), SQLAlchemy 2.x async, Alembic, pytest, asyncpg.

**Design doc:** `docs/plans/2026-04-15-search-title-desc-subject-design.md`

---

## Task 1: Alembic migration 012 — extended weighted search_vector

**Files:**
- Create: `alembic/versions/012_search_vector_extended.py`

**Step 1: Create the migration file**

Content:

```python
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
```

**Step 2: Run upgrade on the dev DB**

Run: `alembic upgrade head`
Expected: migration `012` applied, no errors.

**Step 3: Sanity-check the new vector**

Run via psql / script:
```sql
SELECT search_vector FROM lessons WHERE title = 'Изучение фотоэффекта' LIMIT 1;
```
Expected: output contains tokens with weights — e.g. `'изучен':1A`, `'физик':NB` (subject), `'11':NB` (grade), `'лаборатор':NC` (description).

**Step 4: Commit**

```bash
git add alembic/versions/012_search_vector_extended.py
git commit -m "feat(search): migration 012 — weighted FTS over title+desc+subject+grade"
```

---

## Task 2: Simplify SearchService (remove OR-fallback and ABBR filter)

**Files:**
- Modify: `src/core/services/search.py`
- Modify: `tests/test_search.py` (update tests that refer to removed symbols)

**Step 1: Write the failing test for simplified fts_search contract**

Add to `tests/test_search.py`:

```python
def test_build_tsquery_always_uses_plainto():
    """No OR tsquery helper should exist; AND-only via plainto_tsquery."""
    from src.core.services import search as search_mod
    assert not hasattr(search_mod, "_build_or_tsquery")
    assert not hasattr(search_mod, "_abbr_filters")
    assert not hasattr(search_mod, "_ABBR_RE")
```

**Step 2: Run test — expect FAIL**

Run: `pytest tests/test_search.py::test_build_tsquery_always_uses_plainto -v`
Expected: FAIL (symbols still exist).

**Step 3: Edit `src/core/services/search.py`**

Remove:
- `import re` (if unused after edits)
- `_ABBR_RE`
- `_build_or_tsquery`
- `_abbr_filters`

Replace `_fts_count` / `_fts_fetch` signatures to drop `abbr_conds`:

```python
async def _fts_count(self, session: AsyncSession, ts_query) -> int:
    count_q = select(func.count(Lesson.id)).where(Lesson.search_vector.op("@@")(ts_query))
    return (await session.execute(count_q)).scalar() or 0

async def _fts_fetch(self, session: AsyncSession, ts_query, page: int | None = None) -> list[LessonResult]:
    na_last = case((Lesson.url == "N/A", 1), else_=0)
    q = (
        select(Lesson)
        .options(joinedload(Lesson.subject))
        .where(Lesson.search_vector.op("@@")(ts_query))
        .order_by(na_last, func.ts_rank(Lesson.search_vector, ts_query).desc())
    )
    if page is not None:
        q = q.offset((page - 1) * self.per_page).limit(self.per_page)
    result = await session.execute(q)
    return [
        LessonResult(
            title=l.title, url=l.url,
            description=l.description,
            subject=l.subject.name,
            grade=l.grade,
            section=l.section,
            topic=l.topic,
            is_semantic=False,
        )
        for l in result.scalars().unique().all()
    ]
```

Replace `fts_search` and `fts_search_all`:

```python
async def fts_search(self, session: AsyncSession, query: str, page: int = 1) -> tuple[list[LessonResult], int]:
    ts_query = _build_tsquery(query)
    total = await self._fts_count(session, ts_query)
    if total == 0:
        return [], 0
    lessons = await self._fts_fetch(session, ts_query, page=page)
    return lessons, total

async def fts_search_all(self, session: AsyncSession, query: str) -> list[LessonResult]:
    ts_query = _build_tsquery(query)
    return await self._fts_fetch(session, ts_query)
```

Update `_build_level_results` — it still calls `_build_tsquery(query)` for the AND-ID fetch. Nothing changes there.

**Step 4: Run tests — expect PASS**

Run: `pytest tests/test_search.py -v`
Expected: all previously passing tests still pass; new `test_build_tsquery_always_uses_plainto` passes.

**Step 5: Commit**

```bash
git add src/core/services/search.py tests/test_search.py
git commit -m "refactor(search): drop OR fallback and ABBR filter; single AND pass"
```

---

## Task 3: Golden-set fixture

**Files:**
- Create: `tests/fixtures/examples.csv` (copy from repo root)

**Step 1: Copy the CSV**

```bash
mkdir -p tests/fixtures
cp examples.csv tests/fixtures/examples.csv
```

**Step 2: Verify**

Run: `head -2 tests/fixtures/examples.csv`
Expected: first line is the 8 queries, second line is the first expected row.

**Step 3: Commit**

```bash
git add tests/fixtures/examples.csv
git commit -m "test(search): add golden-set fixture for integration test"
```

---

## Task 4: Integration test — golden set

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_search_golden.py`

**Step 1: Create the package marker**

```bash
mkdir -p tests/integration
touch tests/integration/__init__.py
```

**Step 2: Write the integration test**

`tests/integration/test_search_golden.py`:

```python
"""Golden-set regression for the extended FTS.

Skipped unless DATABASE_URL is set — requires a DB with lesson data.
"""
import csv
import os
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.services.search import SearchService

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="integration test requires DATABASE_URL",
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "examples.csv"

# (min_expected, top_must_contain_any_of)
#   min_expected: L1 must return at least this many rows.
#   top_must_contain_any_of: at least one of the top-5 titles must be from the expected column.
GOLDEN_EXPECTATIONS = {
    "пушкин": (5, ["литератур"]),
    "впр по химии": (2, ["ВПР"]),
    "великая отечественная война": (8, ["Великая Отечественная"]),
    "лабораторные по физике": (5, ["Изучение", "Исследование"]),
    "лабораторные работы": (50, ["лаборатор", "Лабораторн"]),
}

# Queries that are expected to be hard for L1 (digit↔roman, vocabulary gap);
# they must be rescued by L2 semantic search.
L2_ONLY = {
    "петр 1": 3,
    "2 закон ньютона": 3,
    "подготовка к ЕГЭ по физике": 5,
}


@pytest.fixture
async def session():
    url = os.environ["DATABASE_URL"]
    engine = create_async_engine(url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


def _load_queries():
    with open(FIXTURE, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    return rows[0]  # header row = queries


@pytest.mark.asyncio
async def test_l1_golden(session: AsyncSession):
    service = SearchService()
    queries = _load_queries()
    for q in queries:
        if q not in GOLDEN_EXPECTATIONS:
            continue
        min_expected, needles = GOLDEN_EXPECTATIONS[q]
        lessons, total = await service.fts_search(session, q, page=1)
        assert total >= min_expected, f"{q!r}: got {total}, expected >= {min_expected}"
        top_titles = " ".join(l.title for l in lessons)
        assert any(n.lower() in top_titles.lower() for n in needles), (
            f"{q!r}: top-5 titles {[l.title for l in lessons]!r} "
            f"contain none of {needles!r}"
        )


@pytest.mark.asyncio
async def test_l2_rescues_hard_queries(session: AsyncSession):
    service = SearchService()
    for q, min_count in L2_ONLY.items():
        result = await service.search_by_level(session, q, level=2, page=1)
        assert result.total >= min_count, (
            f"L2 {q!r}: got {result.total}, expected >= {min_count}"
        )
```

**Step 3: Run the integration test against the live DB**

Run: `pytest tests/integration/test_search_golden.py -v`
Expected: both tests pass against current (post-migration-012) DB.

**Step 4: Commit**

```bash
git add tests/integration/__init__.py tests/integration/test_search_golden.py
git commit -m "test(search): integration golden-set against examples.csv"
```

---

## Task 5: Manual smoke via production bot commands

**Step 1: Pick 3 queries and run through the search service**

Use the dev shell (or a tiny script):

```python
import asyncio, os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from src.core.services.search import SearchService

async def main():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        svc = SearchService()
        for q in ["пушкин", "лабораторные по физике", "впр по химии"]:
            r = await svc.search_by_level(s, q, level=1, page=1)
            print(q, "→", r.total, [l.title for l in r.lessons])
    await engine.dispose()

asyncio.run(main())
```

Expected: totals and top titles match the golden table (see design doc).

**Step 2: Commit nothing (manual verification only).**

---

## Task 6: Update tasks/lessons.md

**Files:**
- Modify: `tasks/lessons.md`

**Step 1: Append a short lessons-learned entry**

```markdown
## Search — structural limits of pure FTS (2026-04-15)

Two classes of queries are not solvable by any FTS configuration alone:

1. **Numeric form mismatch.** `петр 1` vs stored `Пётр I`; `2 закон` vs
   stored `Второй закон`. Tokenizer treats `1` and `i` as unrelated tokens.
   Rely on L2 (semantic) or tell users to spell ordinals / Roman numerals.
2. **Vocabulary gap.** Users type intent words (`подготовка`) that are
   absent from both titles and descriptions. Classic semantic-search case.

When adding fields to `search_vector`, check subject/grade too — they live
in separate tables (`subjects`) and tokens like «физика» may be missing
from `title`/`description` even for obviously-physics lessons.
```

**Step 2: Commit**

```bash
git add tasks/lessons.md
git commit -m "docs(lessons): capture FTS structural limits from search rework"
```

---

## Task 7: Final verification

**Step 1: Full test suite**

Run: `pytest tests/ -v --ignore=tests/integration`
Expected: all non-integration tests pass (2 pre-existing `test_models.py` failures unrelated to search stay failing — documented baseline).

Run: `pytest tests/integration/ -v` (with `DATABASE_URL` set)
Expected: both integration tests pass.

**Step 2: Verify branch**

Run: `git log --oneline feature/search-extended-fts ^dev_2_levels`
Expected: commits from Tasks 1, 2, 3, 4, 6 in order. No stray work.

**Step 3: Hand off via finishing-a-development-branch skill**

Invoke `superpowers:finishing-a-development-branch` when done.

---

## Rollback plan

If the new behaviour causes regressions in production:

1. `alembic downgrade 011` — restores title-only tsvector.
2. `git revert` the code refactor commit (Task 2).

Both changes are additive-safe: the `search_vector` column and GIN index
stay in place across migrations.
