# Fix FTS Search: OR Logic + Section/Topic in Search Vector

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix two search bugs: (1) multi-word queries use AND instead of OR, missing relevant results; (2) search vector only contains title+description, missing section/topic names.

**Architecture:** Use `websearch_to_tsquery` with OR-joined words for inclusive multi-word search. Update the PostgreSQL trigger to lookup section/topic names via subselect when building search_vector. New Alembic migration for the trigger fix + vector rebuild.

**Tech Stack:** PostgreSQL FTS (websearch_to_tsquery), Alembic, SQLAlchemy, pytest

---

### Task 1: Fix FTS query to use OR for multi-word searches

**Files:**
- Modify: `src/core/services/search.py:22-34` (fts_search method)
- Test: `tests/test_search.py`

**Step 1: Write failing test**

```python
# tests/test_search.py — add this test

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from sqlalchemy import text

from src.core.services.search import SearchService, _build_tsquery


@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
def test_build_tsquery_single_word(mock_settings):
    """Single word should use plainto_tsquery (no change)."""
    expr = _build_tsquery("тангенс")
    # Should produce plainto_tsquery('russian', 'тангенс')
    compiled = expr.compile(compile_kwargs={"literal_binds": True})
    assert "plainto_tsquery" in str(compiled)


@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
def test_build_tsquery_multi_word_uses_or(mock_settings):
    """Multiple words should use websearch_to_tsquery with OR."""
    expr = _build_tsquery("тангенс котангенс")
    compiled = expr.compile(compile_kwargs={"literal_binds": True})
    assert "websearch_to_tsquery" in str(compiled)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_search.py::test_build_tsquery_single_word tests/test_search.py::test_build_tsquery_multi_word_uses_or -v`
Expected: FAIL — `_build_tsquery` doesn't exist yet

**Step 3: Implement `_build_tsquery` and update `fts_search`**

In `src/core/services/search.py`, add helper function and update fts_search:

```python
from sqlalchemy import func

def _build_tsquery(query: str):
    """Build tsquery: single word uses plainto_tsquery, multiple words use OR via websearch_to_tsquery."""
    words = query.strip().split()
    if len(words) <= 1:
        return func.plainto_tsquery("russian", query)
    or_query = " OR ".join(words)
    return func.websearch_to_tsquery("russian", or_query)
```

Then in `fts_search`, replace:
```python
ts_query = func.plainto_tsquery("russian", query)
```
with:
```python
ts_query = _build_tsquery(query)
```

**Step 4: Run tests**

Run: `pytest tests/test_search.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/core/services/search.py tests/test_search.py
git commit -m "fix: use OR logic for multi-word FTS queries"
```

---

### Task 2: Update search vector trigger to include section/topic names

**Files:**
- Create: `alembic/versions/005_search_vector_with_section_topic.py`
- Test: manual verification via `alembic upgrade head` (trigger is DB-level, not unit-testable without a real DB)

**Step 1: Create the migration**

```python
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
        FROM (
            SELECT l.id,
                   sec.name as section_name,
                   top.name as topic_name
            FROM lessons l
            LEFT JOIN sections sec ON l.section_id = sec.id
            LEFT JOIN topics top ON l.topic_id = top.id
        ) sub
        LEFT JOIN sections s ON lessons.section_id = s.id
        LEFT JOIN topics t ON lessons.topic_id = t.id
        WHERE lessons.id = sub.id
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
```

NOTE: The rebuild UPDATE is intentionally simplified — the trigger itself handles future inserts correctly. The UPDATE just ensures existing data gets the new vector.

**Step 2: Verify migration syntax**

Run: `python -c "import alembic.versions" 2>&1 || echo OK` (basic import check)
Run: `alembic check` or `alembic heads` to verify chain

**Step 3: Commit**

```bash
git add alembic/versions/005_search_vector_with_section_topic.py
git commit -m "fix: include section/topic names in search vector trigger"
```

---

### Task 3: Verify end-to-end

**Step 1: Run all tests**

Run: `pytest tests/ -v`
Expected: all pass

**Step 2: Verify migration chain**

Run: `alembic heads`
Expected: single head at 005

**Step 3: Manual test plan (on staging/dev DB)**

1. `alembic upgrade head` — migration applies cleanly
2. Query: `SELECT websearch_to_tsquery('russian', 'тангенс OR котангенс');` — returns `'тангенс' | 'котангенс'`
3. Query: `SELECT title FROM lessons WHERE search_vector @@ websearch_to_tsquery('russian', 'тангенс OR котангенс') LIMIT 5;` — returns lessons about either тангенс or котангенс
4. Check a lesson with section/topic: `SELECT search_vector FROM lessons WHERE section_id IS NOT NULL LIMIT 1;` — vector should contain section name tokens

---

## Summary of changes

| What | Before | After |
|------|--------|-------|
| Multi-word FTS | `plainto_tsquery` (AND) | `websearch_to_tsquery` (OR) |
| Search vector | title + description | title + description + section name + topic name |
| Weight scheme | A=title, B=description | A=title, B=description, C=section/topic |
