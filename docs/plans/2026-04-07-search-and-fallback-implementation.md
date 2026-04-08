# Search AND→OR Fallback Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace OR-based FTS with AND-first cascade that falls back to OR+semantic when AND yields too few results.

**Architecture:** `_build_tsquery` becomes AND-only; a new `_build_tsquery_or` preserves the old OR logic; `hybrid_search` tries AND first and falls back to the existing OR+semantic path when `total < fts_min_results`.

**Tech Stack:** PostgreSQL FTS (`plainto_tsquery`, `websearch_to_tsquery`), SQLAlchemy async, pytest.

---

### Task 1: Update `_build_tsquery` to AND and add `_build_tsquery_or`

**Files:**
- Modify: `src/core/services/search.py:15-20`
- Test: `tests/test_search.py`

**Step 1: Update the failing tests for `_build_tsquery`**

In `tests/test_search.py`, replace the existing `test_build_tsquery_multiple_words` test and add an OR test:

```python
def test_build_tsquery_single_word():
    expr = _build_tsquery("тангенс")
    sql = str(expr.compile())
    assert "plainto_tsquery" in sql


def test_build_tsquery_multiple_words_uses_and():
    # AND logic: plainto_tsquery handles multi-word with AND
    expr = _build_tsquery("тангенс котангенс")
    sql = str(expr.compile())
    assert "plainto_tsquery" in sql


def test_build_tsquery_or_multiple_words():
    from src.core.services.search import _build_tsquery_or
    expr = _build_tsquery_or("тангенс котангенс")
    sql = str(expr.compile())
    assert "websearch_to_tsquery" in sql
    assert "OR" in sql


def test_build_tsquery_or_single_word():
    from src.core.services.search import _build_tsquery_or
    expr = _build_tsquery_or("тангенс")
    sql = str(expr.compile())
    assert "plainto_tsquery" in sql
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_search.py::test_build_tsquery_multiple_words_uses_and tests/test_search.py::test_build_tsquery_or_multiple_words -v
```
Expected: FAIL — `test_build_tsquery_multiple_words_uses_and` fails because current code uses websearch_to_tsquery, `test_build_tsquery_or_multiple_words` fails because `_build_tsquery_or` doesn't exist.

**Step 3: Implement the change in `search.py`**

Replace the `_build_tsquery` function and add `_build_tsquery_or`:

```python
def _build_tsquery(query: str):
    """AND logic: all words must be present. Uses plainto_tsquery for all cases."""
    return func.plainto_tsquery("russian", query)


def _build_tsquery_or(query: str):
    """OR logic: any word matches. Used as fallback when AND yields too few results."""
    words = query.strip().split()
    if len(words) <= 1:
        return func.plainto_tsquery("russian", query)
    return func.websearch_to_tsquery("russian", " OR ".join(words))
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_search.py::test_build_tsquery_single_word tests/test_search.py::test_build_tsquery_multiple_words_uses_and tests/test_search.py::test_build_tsquery_or_multiple_words tests/test_search.py::test_build_tsquery_or_single_word -v
```
Expected: all 4 PASS.

**Step 5: Run full test suite to check nothing broke**

```bash
pytest tests/test_search.py -v
```
Expected: all pass.

**Step 6: Commit**

```bash
git add src/core/services/search.py tests/test_search.py
git commit -m "feat: switch FTS to AND logic, add _build_tsquery_or for fallback"
```

---

### Task 2: Update `hybrid_search` to use AND→OR cascade

**Files:**
- Modify: `src/core/services/search.py:102-125`
- Test: `tests/test_search.py`

**Step 1: Write the failing test**

Add to `tests/test_search.py`:

```python
@pytest.mark.asyncio
@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
async def test_hybrid_search_uses_or_fallback_when_and_insufficient(mock_settings):
    """When AND FTS returns fewer than fts_min_results, OR FTS is used."""
    service = SearchService()

    and_lesson = LessonResult(
        title="Петр Великий", url="https://example.com",
        subject="История", grade=8, section="Раздел 1", topic="Петр I",
    )
    or_lesson = LessonResult(
        title="Вариант 1", url="https://example.com/2",
        subject="Математика", grade=5, section="Раздел 1", topic="Тема 1",
    )

    # AND search returns 0 results (below fts_min_results=3)
    # OR search returns lessons
    with patch.object(service, "fts_search", new_callable=AsyncMock) as mock_fts, \
         patch.object(service, "semantic_search", new_callable=AsyncMock) as mock_sem:

        # First call: AND search (returns 0)
        # Second call: OR search (returns results)
        mock_fts.side_effect = [
            ([], 0),          # AND call
            ([or_lesson], 1), # OR call
        ]
        mock_sem.return_value = []

        result = await service.hybrid_search(MagicMock(), "Петр 1")

    assert mock_fts.call_count == 2
    assert result.total == 1


@pytest.mark.asyncio
@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
async def test_hybrid_search_uses_and_when_sufficient(mock_settings):
    """When AND FTS returns >= fts_min_results, OR is never called."""
    service = SearchService()

    lessons = [
        LessonResult(
            title=f"Урок {i}", url=f"https://example.com/{i}",
            subject="История", grade=8, section="Раздел", topic="Тема",
        )
        for i in range(5)
    ]

    with patch.object(service, "fts_search", new_callable=AsyncMock) as mock_fts, \
         patch.object(service, "semantic_search", new_callable=AsyncMock) as mock_sem:

        mock_fts.return_value = (lessons, 5)
        mock_sem.return_value = []

        result = await service.hybrid_search(MagicMock(), "история петр")

    assert mock_fts.call_count == 1  # only AND, no OR fallback
    assert result.total == 5
```

Also add imports at top of `tests/test_search.py`:
```python
import pytest
from unittest.mock import AsyncMock
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_search.py::test_hybrid_search_uses_or_fallback_when_and_insufficient tests/test_search.py::test_hybrid_search_uses_and_when_sufficient -v
```
Expected: FAIL.

**Step 3: Update `hybrid_search` in `search.py`**

Replace the `hybrid_search` method:

```python
async def hybrid_search(self, session: AsyncSession, query: str, page: int = 1) -> SearchResult:
    # Step 1: try AND FTS (precise)
    fts_lessons, fts_total = await self.fts_search(session, query, page=1)

    if fts_total >= self.fts_min_results:
        # AND gave enough results — paginate and return
        if page > 1:
            fts_lessons, _ = await self.fts_search(session, query, page=page)
        return SearchResult(query=query, lessons=fts_lessons, total=fts_total, page=page, per_page=self.per_page)

    # Step 2: AND insufficient — fall back to OR FTS + semantic
    or_lessons, or_total = await self.fts_search(session, query, page=1, use_or=True)

    if or_total >= self.fts_min_results:
        if page > 1:
            or_lessons, _ = await self.fts_search(session, query, page=page, use_or=True)
        return SearchResult(query=query, lessons=or_lessons, total=or_total, page=page, per_page=self.per_page)

    # Step 3: OR also insufficient — add semantic
    or_id_query = select(Lesson.id).where(
        Lesson.search_vector.op("@@")(_build_tsquery_or(query))
    )
    or_id_result = await session.execute(or_id_query)
    exclude_ids = [row[0] for row in or_id_result.all()]

    semantic_lessons = await self.semantic_search(session, query, exclude_ids=exclude_ids)
    combined = or_lessons + semantic_lessons
    total = len(combined)

    offset = (page - 1) * self.per_page
    page_lessons = combined[offset: offset + self.per_page]

    return SearchResult(query=query, lessons=page_lessons, total=total, page=page, per_page=self.per_page)
```

Also update `fts_search` signature to accept `use_or` flag:

```python
async def fts_search(self, session: AsyncSession, query: str, page: int = 1, use_or: bool = False) -> tuple[list[LessonResult], int]:
    ts_query = _build_tsquery_or(query) if use_or else _build_tsquery(query)
    # rest of method unchanged
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_search.py::test_hybrid_search_uses_or_fallback_when_and_insufficient tests/test_search.py::test_hybrid_search_uses_and_when_sufficient -v
```
Expected: PASS.

**Step 5: Run full test suite**

```bash
pytest tests/ -v
```
Expected: all pass.

**Step 6: Commit**

```bash
git add src/core/services/search.py tests/test_search.py
git commit -m "feat: AND→OR cascade in hybrid_search, fallback when AND insufficient"
```

---

### Task 3: Update `fts_search_all` to use AND logic

**Files:**
- Modify: `src/core/services/search.py:177-199`

This method is used for clarification analysis and should be consistent with the main search path.

**Step 1: Verify `fts_search_all` uses the old OR-capable `_build_tsquery`**

Read `src/core/services/search.py` lines 177-199. It calls `_build_tsquery(query)` — after Task 1, this already uses AND. No code change needed here.

**Step 2: Verify with existing tests**

```bash
pytest tests/ -v
```
Expected: all pass.

**Step 3: Commit (only if any change was needed)**

```bash
git add src/core/services/search.py
git commit -m "fix: fts_search_all consistent with AND search logic"
```

---

## Testing the full flow manually

After all tasks are complete, test with the bot using a query like "Петр 1":
- Expected: results about Пётр I (история), not "Вариант 1" lessons
- If AND returns 0 → should fall back to OR results
