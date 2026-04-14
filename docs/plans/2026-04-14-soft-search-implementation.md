# Soft Search — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace strict AND `plainto_tsquery` at level 1 with an OR+prefix FTS plus a pg_trgm fallback on `title`, so typos and extra words no longer force users into the semantic-search button.

**Architecture:** Single-pass search in `SearchService.fts_search` / `fts_search_all` that unions two sources — OR-FTS on `search_vector` and trigram similarity on `title` — ranked on a shared `[0,1]` score. Level-2 semantic flow is untouched. Feature-flagged via `enable_fuzzy_search` for safe rollback.

**Tech Stack:** Python 3.12, SQLAlchemy async, PostgreSQL (pg_trgm extension), Alembic, pytest + pytest-asyncio.

**Design reference:** `docs/plans/2026-04-13-soft-search-design.md`.

**Scope note on columns:** Migration `011_search_vector_title_only.py` narrowed `search_vector` to `title` only. Accordingly, trigram index and trigram similarity are applied **only to `title`** — not to `description`/`section`/`topic`. This overrides the earlier design section 2.

---

## Working conventions

- All paths are relative to the worktree root: `C:\Users\aleks\Documents\Projects\bot_aitsok\.worktrees\soft-search`.
- Tests are mock-based (no live DB in `tests/`). SQL-correctness of the new query is verified by a **manual checklist at the end** (Task 10) against a dev Postgres.
- Conventional Commits. Each task ends with one commit.
- Run tests with: `pytest tests/ -v --tb=short` from the worktree root.

---

### Task 1: Add config fields for fuzzy search

**Files:**
- Modify: `src/config.py` (append to `Settings` class next to existing search fields)

**Step 1: Write the failing test**

Create `tests/test_config_fuzzy.py`:

```python
from src.config import get_settings


def test_fuzzy_search_defaults():
    s = get_settings()
    assert s.enable_fuzzy_search is True
    assert s.trigram_similarity_threshold == 0.3
    assert s.trigram_title_weight == 1.0
    assert s.fts_score_floor == 0.5
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config_fuzzy.py -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'enable_fuzzy_search'`.

**Step 3: Add the fields**

Add inside `Settings` (after `search_clarify_threshold`):

```python
enable_fuzzy_search: bool = True
trigram_similarity_threshold: float = 0.3
trigram_title_weight: float = 1.0
fts_score_floor: float = 0.5
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_config_fuzzy.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/config.py tests/test_config_fuzzy.py
git commit -m "feat(config): add fuzzy search settings"
```

---

### Task 2: Alembic migration — pg_trgm extension + title trigram index

**Files:**
- Create: `alembic/versions/012_pg_trgm_title_index.py`

**Step 1: Write migration**

```python
"""Enable pg_trgm and add trigram index on lessons.title.

Revision ID: 012
Revises: 011
Create Date: 2026-04-14
"""

from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS lessons_title_trgm_idx "
        "ON lessons USING GIN (title gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS lessons_title_trgm_idx")
    # Intentionally do NOT drop the extension — other code may depend on it.
```

**Step 2: Verify pg_trgm is available on target environment**

Manual pre-flight (document only, do not run now):
- On dev PostgreSQL, confirm `SELECT * FROM pg_available_extensions WHERE name='pg_trgm';` returns a row.
- On managed prod, confirm no ticket / superuser is required.

**Step 3: Apply migration locally**

Run: `alembic upgrade head` (only if you have a local DB ready; otherwise skip until Task 10).

Expected: new migration applied, index created, no errors.

**Step 4: Commit**

```bash
git add alembic/versions/012_pg_trgm_title_index.py
git commit -m "feat(db): enable pg_trgm and add title trigram index"
```

---

### Task 3: Add query normalizer helper

**Files:**
- Modify: `src/core/services/search.py` (add a new private helper near `_build_tsquery`)
- Create tests in: `tests/test_search_normalize.py`

**Step 1: Write the failing tests**

```python
from src.core.services.search import _normalize_tokens


def test_normalize_splits_and_lowercases():
    assert _normalize_tokens("Теорема Пифагора") == ["теорема", "пифагора"]


def test_normalize_drops_single_char_non_digit():
    assert _normalize_tokens("а теорема") == ["теорема"]


def test_normalize_keeps_digits():
    assert _normalize_tokens("7 класс") == ["7", "класс"]


def test_normalize_strips_tsquery_specials():
    assert _normalize_tokens("теорема & | ! ( ) : *") == ["теорема"]


def test_normalize_empty_string():
    assert _normalize_tokens("   ") == []
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_search_normalize.py -v`
Expected: FAIL with `ImportError: cannot import name '_normalize_tokens'`.

**Step 3: Implement**

Add to `src/core/services/search.py` (top, near other helpers):

```python
import re

_TSQUERY_SPECIALS = re.compile(r"[&|!():*]")
_SPLIT_RE = re.compile(r"\s+")


def _normalize_tokens(query: str) -> list[str]:
    """Lowercase, strip tsquery specials, split into tokens,
    drop single-char non-digit tokens."""
    if not query:
        return []
    cleaned = _TSQUERY_SPECIALS.sub(" ", query.lower())
    raw = [t.strip(".,;:!?\"'()[]{}") for t in _SPLIT_RE.split(cleaned)]
    return [t for t in raw if t and (len(t) >= 2 or t.isdigit())]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_search_normalize.py -v`
Expected: 5 PASS.

**Step 5: Commit**

```bash
git add src/core/services/search.py tests/test_search_normalize.py
git commit -m "feat(search): add query token normalizer"
```

---

### Task 4: Add OR+prefix tsquery builder

**Files:**
- Modify: `src/core/services/search.py`
- Add tests to: `tests/test_search_normalize.py`

**Step 1: Write failing tests**

Append to `tests/test_search_normalize.py`:

```python
from src.core.services.search import _build_or_tsquery_string


def test_build_or_tsquery_single_token():
    assert _build_or_tsquery_string(["теорема"]) == "теорема:*"


def test_build_or_tsquery_multi_tokens():
    assert _build_or_tsquery_string(["теорема", "пифагора"]) == "теорема:* | пифагора:*"


def test_build_or_tsquery_empty():
    assert _build_or_tsquery_string([]) == ""
```

**Step 2: Run test**

Run: `pytest tests/test_search_normalize.py -v`
Expected: 3 new FAIL (ImportError).

**Step 3: Implement**

Add to `src/core/services/search.py`:

```python
def _build_or_tsquery_string(tokens: list[str]) -> str:
    """Build a tsquery OR-string with prefix matching: 'tok1:* | tok2:*'."""
    return " | ".join(f"{t}:*" for t in tokens)
```

**Step 4: Run**

Run: `pytest tests/test_search_normalize.py -v`
Expected: all PASS.

**Step 5: Commit**

```bash
git add src/core/services/search.py tests/test_search_normalize.py
git commit -m "feat(search): add OR+prefix tsquery builder"
```

---

### Task 5: Implement `fts_search_fuzzy` — unified OR-FTS + trigram SQL

**Files:**
- Modify: `src/core/services/search.py`

**Context:** This is the core change. We add a new async method `fts_search_fuzzy(session, query, page=1)` with the same signature as `fts_search` but using the new pipeline. Old `fts_search` is kept for the rollback flag.

**Step 1: Implement the method**

Add inside `SearchService`:

```python
async def fts_search_fuzzy(
    self, session: AsyncSession, query: str, page: int = 1
) -> tuple[list[LessonResult], int]:
    """OR-FTS with prefix, unioned with pg_trgm fallback on title.
    Returns (page_results, total_count). Falls back to empty on empty query."""
    from sqlalchemy import literal, text, union_all

    tokens = _normalize_tokens(query)
    if not tokens:
        return [], 0

    ts_str = _build_or_tsquery_string(tokens)
    ts_query = func.to_tsquery("russian", ts_str)
    full_q = " ".join(tokens)
    thr = self.trigram_threshold
    floor = self.fts_floor
    title_w = self.trigram_title_w

    # Build one CTE-based query that unions FTS and trigram hits,
    # deduplicates, and ranks on a single 0..1 score.
    sql = text(f"""
        WITH fts AS (
            SELECT id,
                   {floor} + {1 - floor} * LEAST(ts_rank(search_vector, :ts), 1.0) AS score
            FROM lessons
            WHERE search_vector @@ :ts
        ),
        trg AS (
            SELECT id,
                   {title_w} * similarity(title, :q) AS score
            FROM lessons
            WHERE similarity(title, :q) > :thr
        ),
        merged AS (
            SELECT id, MAX(score) AS score FROM (
                SELECT id, score FROM fts
                UNION ALL
                SELECT id, score FROM trg
            ) u
            GROUP BY id
        )
        SELECT m.id, m.score
        FROM merged m
        JOIN lessons l ON l.id = m.id
        ORDER BY (CASE WHEN l.url = 'N/A' THEN 1 ELSE 0 END),
                 m.score DESC,
                 m.id
    """)

    rows = (await session.execute(
        sql, {"ts": ts_str, "q": full_q, "thr": thr}
    )).all()

    total = len(rows)
    offset = (page - 1) * self.per_page
    page_ids = [r.id for r in rows[offset:offset + self.per_page]]
    if not page_ids:
        return [], total

    q = (
        select(Lesson)
        .options(joinedload(Lesson.subject))
        .where(Lesson.id.in_(page_ids))
    )
    result = await session.execute(q)
    by_id = {l.id: l for l in result.scalars().unique().all()}

    lessons = [
        LessonResult(
            title=by_id[i].title, url=by_id[i].url,
            description=by_id[i].description,
            subject=by_id[i].subject.name,
            grade=by_id[i].grade,
            section=by_id[i].section,
            topic=by_id[i].topic,
            is_semantic=False,
        )
        for i in page_ids if i in by_id
    ]
    return lessons, total
```

**Step 2: Extend `__init__` to read new settings**

In `SearchService.__init__`, add:

```python
self.trigram_threshold = settings.trigram_similarity_threshold
self.trigram_title_w = settings.trigram_title_weight
self.fts_floor = settings.fts_score_floor
self.fuzzy_enabled = settings.enable_fuzzy_search
```

**Step 3: Commit**

```bash
git add src/core/services/search.py
git commit -m "feat(search): add fuzzy FTS+trigram search method"
```

Note: no unit test here — this method hits real SQL (pg_trgm, CTE). It is covered by the manual checklist in Task 10.

---

### Task 6: Add `fts_search_all_fuzzy` (no pagination) for clarification flow

**Files:**
- Modify: `src/core/services/search.py`

**Step 1: Implement**

Add inside `SearchService`, mirroring the existing `fts_search_all` pattern but using the fuzzy SQL from Task 5 without pagination:

```python
async def fts_search_all_fuzzy(
    self, session: AsyncSession, query: str
) -> list[LessonResult]:
    """Same as fts_search_fuzzy but returns all hits (no pagination)."""
    lessons, total = await self.fts_search_fuzzy(session, query, page=1)
    if total <= self.per_page:
        return lessons
    # Re-fetch all: simplest correct path — call with large page size via loop.
    # The CTE is cheap; one more round-trip is acceptable for clarification.
    all_lessons: list[LessonResult] = []
    page = 1
    while True:
        batch, total = await self.fts_search_fuzzy(session, query, page=page)
        if not batch:
            break
        all_lessons.extend(batch)
        if len(all_lessons) >= total:
            break
        page += 1
    return all_lessons
```

**Step 2: Commit**

```bash
git add src/core/services/search.py
git commit -m "feat(search): add non-paginated fuzzy search"
```

---

### Task 7: Wire routing in `search_by_level` and `get_all_lessons_for_level`

**Files:**
- Modify: `src/core/services/search.py`

**Step 1: Write failing tests**

Create `tests/test_search_routing.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from src.core.services.search import SearchService


def _mock_settings(**overrides):
    def factory():
        m = MagicMock()
        m.fts_min_results = 3
        m.semantic_similarity_threshold = 0.75
        m.results_per_page = 5
        m.search_clarify_threshold = 10
        m.enable_fuzzy_search = True
        m.trigram_similarity_threshold = 0.3
        m.trigram_title_weight = 1.0
        m.fts_score_floor = 0.5
        for k, v in overrides.items():
            setattr(m, k, v)
        return m
    return factory


@pytest.mark.asyncio
@patch("src.core.services.search.get_settings", side_effect=_mock_settings())
async def test_level_1_uses_fuzzy_when_flag_on(_):
    service = SearchService()
    with patch.object(service, "fts_search_fuzzy", new_callable=AsyncMock) as m_fuzzy, \
         patch.object(service, "fts_search", new_callable=AsyncMock) as m_strict:
        m_fuzzy.return_value = ([], 0)
        await service.search_by_level(MagicMock(), "q", level=1)
    assert m_fuzzy.call_count == 1
    assert m_strict.call_count == 0


@pytest.mark.asyncio
@patch("src.core.services.search.get_settings", side_effect=_mock_settings(enable_fuzzy_search=False))
async def test_level_1_uses_strict_when_flag_off(_):
    service = SearchService()
    with patch.object(service, "fts_search_fuzzy", new_callable=AsyncMock) as m_fuzzy, \
         patch.object(service, "fts_search", new_callable=AsyncMock) as m_strict:
        m_strict.return_value = ([], 0)
        await service.search_by_level(MagicMock(), "q", level=1)
    assert m_strict.call_count == 1
    assert m_fuzzy.call_count == 0
```

**Step 2: Run tests**

Run: `pytest tests/test_search_routing.py -v`
Expected: FAIL (routing not yet updated).

**Step 3: Update `search_by_level` and `get_all_lessons_for_level`**

In `search_by_level`, replace the level-1 branch to choose based on `self.fuzzy_enabled`:

```python
if level == 1:
    if self.fuzzy_enabled:
        lessons, total = await self.fts_search_fuzzy(session, query, page=page)
    else:
        lessons, total = await self.fts_search(session, query, page=page)
    return SearchResult(
        query=query, lessons=lessons, total=total,
        page=page, per_page=self.per_page,
    )
```

In `get_all_lessons_for_level` (level 1 branch), similarly:

```python
if level == 1:
    if self.fuzzy_enabled:
        return await self.fts_search_all_fuzzy(session, query)
    return await self.fts_search_all(session, query)
```

**Step 4: Run tests**

Run: `pytest tests/test_search_routing.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/core/services/search.py tests/test_search_routing.py
git commit -m "feat(search): route level-1 through fuzzy when flag enabled"
```

---

### Task 8: Run full test suite to catch regressions

**Step 1: Run everything**

Run: `pytest tests/ -v --tb=short`

Expected: all existing tests still pass. The changes to `search_by_level` should not break `test_search.py::test_search_by_level_1_returns_and_fts` (it patches `fts_search` directly — may need to switch to patching `fts_search_fuzzy` since flag defaults to True).

**Step 2: If a test breaks**

Inspect the test. If it patches `fts_search`, update it to also/instead patch `fts_search_fuzzy`, OR set `enable_fuzzy_search=False` in its mock settings. Prefer the latter to preserve existing semantics of that test; add a **new** test for fuzzy path explicitly. Do NOT delete the old assertion.

**Step 3: Commit any test adjustments**

```bash
git add tests/
git commit -m "test(search): adjust existing tests for fuzzy routing flag"
```

---

### Task 9: Short docstring / module header note

**Files:**
- Modify: `src/core/services/search.py` (top-of-file docstring)

**Step 1:** Add one-paragraph docstring explaining: level 1 uses `fts_search_fuzzy` (OR+prefix FTS unioned with pg_trgm on title) when `enable_fuzzy_search=True`, otherwise strict `fts_search`. Reference the design doc path.

**Step 2: Commit**

```bash
git add src/core/services/search.py
git commit -m "docs(search): note fuzzy search module behavior"
```

---

### Task 10: Manual verification checklist (DB required)

This task is NOT automated. Run against a dev PostgreSQL with real lesson data.

**Pre-flight:**
- [ ] `alembic upgrade head` applies migration 012 without error
- [ ] `SELECT extname FROM pg_extension WHERE extname='pg_trgm';` returns a row
- [ ] `\d lessons` shows `lessons_title_trgm_idx`

**Functional — problem 2 (extra words):**
- [ ] Query "задачи на теорему пифагора 8 класс" returns results matching "теорема Пифагора"
- [ ] Query "теорема пифагора" still returns same/similar top results as before (no regression in precision)

**Functional — problem 1 (typos):**
- [ ] "теорма пифагра" returns "теорема Пифагора" within top 5
- [ ] "пифагр" returns relevant results
- [ ] Pure gibberish like "ъъъ" returns empty (no false positives)

**Rollback flag:**
- [ ] Setting `ENABLE_FUZZY_SEARCH=false` in env restores the old behavior: "теорма" → 0 results

**Edge cases:**
- [ ] Single-char query "а" → empty result
- [ ] "7 класс" → returns grade-7 lessons
- [ ] "математика 7 класс" → clarification kicks in if >10 results

**Record findings** in `docs/plans/2026-04-14-soft-search-implementation.md` under a new "## Verification log" section, then commit:

```bash
git add docs/plans/2026-04-14-soft-search-implementation.md
git commit -m "docs(search): log manual verification results"
```

---

## Verification log

To be filled after running Task 10 against dev PostgreSQL.

**Pre-flight:**
- [ ] `alembic upgrade head` applies migration 012
- [ ] `pg_trgm` extension present
- [ ] `lessons_title_trgm_idx` created

**Functional — extra words:**
- [ ] "задачи на теорему пифагора 8 класс" → matches "теорема Пифагора"
- [ ] "теорема пифагора" → no precision regression

**Functional — typos:**
- [ ] "теорма пифагра" → "теорема Пифагора" in top 5
- [ ] "пифагр" → relevant results
- [ ] "ъъъ" → empty

**Rollback:**
- [ ] `ENABLE_FUZZY_SEARCH=false` restores strict AND ("теорма" → 0)

**Edge:**
- [ ] "а" → empty
- [ ] "7 класс" → grade-7 lessons
- [ ] "математика 7 класс" → clarification fires when >10 results

---

## Completion criteria

- All automated tests green: `pytest tests/ -v`
- Manual checklist (Task 10) passes on dev DB
- Rollback flag verified
- Design doc and implementation plan committed on branch `soft-search`
- Ready for PR from `soft-search` → `dev_2_levels`
