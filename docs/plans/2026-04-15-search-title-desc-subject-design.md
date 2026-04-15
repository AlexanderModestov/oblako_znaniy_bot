# Search rework: FTS over title + description + subject + grade

**Date:** 2026-04-15
**Branch:** `dev_2_levels`
**Author:** brainstorm session (Alex + Claude)

## Problem

Current search (post-migration `011`) indexes only `lessons.title` into the FTS
`search_vector`. Many relevant results are missed because the real signal lives
in `description` (material type, topics, authors) and in the structured fields
`subject.name` / `grade` that are stored relationally and never indexed.

Level 1 also has an OR-fallback (commit `1cbe369`): if strict AND on the title
returns 0, we retry with OR. On a title-only vector this mostly helped, but it
also produces noisy long lists whenever the precise query misses by one rare
word.

Validation against a golden set of 8 queries (`examples.csv`) showed the
current search fails on 4/8 queries and the OR-fallback is responsible for
most of the noise we want to remove.

## Decision summary

| # | Decision |
|---|---|
| 1 | Extend `search_vector` to `title + description + subject.name + grade`. |
| 2 | Keep two search levels: L1 = FTS only, L2 = FTS + semantic (unchanged). |
| 3 | L1 uses strict AND (`plainto_tsquery`). No OR-fallback. |
| 4 | Weights: title=A, subject+grade=B, description=C. |
| 5 | Remove the ABBR filter (`_abbr_filters`, `_ABBR_RE`). |
| 6 | Subject name is embedded into the lesson vector via subquery in the trigger. Renaming a subject will not retroactively reindex lessons (accepted limitation). |

## Golden set validation

Extended vector simulated live against production data:

| # | Query | Old (title-only AND→OR) | Extended AND-only | Expected | Status |
|---|---|---|---|---|---|
| 1 | `пушкин` | 6 | 6 | 7 | OK |
| 2 | `петр 1` | 2 | 2 | 17 | FAIL — digit vs roman |
| 3 | `2 закон ньютона` | 1 | 1 | 8 | FAIL — digit vs ordinal |
| 4 | `подготовка к ЕГЭ по физике` | 0 | 0 | 36 | FAIL — vocabulary gap, L2 job |
| 5 | `впр по химии` | 4 | 4 | 4 | OK |
| 6 | `великая отечественная война` | 13 | 13 | 18 | OK |
| 7 | `лабораторные по физике` | **0** | **12** | 11 | FIXED |
| 8 | `лабораторные работы` | 173 | 173 | ~160 | OK |

5/8 handled cleanly at L1. The 3 remaining failures are systemic, not
fixable by any pure FTS change:

- **#2, #3 (digits ↔ roman/ordinal):** `Пётр I`, `Второй закон Ньютона` are
  stored in prose. `plainto_tsquery('russian', '1')` produces token `1`, which
  does not match token `i`. Ignoring this is acceptable: users who type
  `петр I` or `второй закон` get correct results; others fall through to L2.
- **#4 (vocabulary gap):** the word «подготовка» does not appear in any
  lesson's text — descriptions say «практическая работа», «контрольная
  работа», «тренировка». This is exactly the case L2 (OpenAI embeddings)
  was added for.

## Data layer — migration `012`

New Alembic revision `012_search_vector_extended`:

```sql
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
```

Followed by a one-shot backfill:

```sql
UPDATE lessons SET search_vector =
    setweight(to_tsvector('russian', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('russian',
        coalesce((SELECT name FROM subjects WHERE id = lessons.subject_id), '')
    ), 'B') ||
    setweight(to_tsvector('russian', coalesce(grade::text, '')), 'B') ||
    setweight(to_tsvector('russian', coalesce(description, '')), 'C');
```

The GIN index `ix_lessons_search_vector` is unchanged. Downgrade reverts to
the title-only definition from `011`.

**Known limitation:** if `subjects.name` is edited, lessons do not get
reindexed. The subjects table is a stable reference; if the need arises, a
later migration can add a trigger on `subjects` that cascades an UPDATE on
`lessons`.

## Code layer — `src/core/services/search.py`

**Remove:**
- `_ABBR_RE` and `_abbr_filters()`.
- `_build_or_tsquery()`.
- The OR-fallback branches in `fts_search()` and `fts_search_all()`.

**Simplify:**

```python
async def fts_search(self, session, query, page=1) -> tuple[list[LessonResult], int]:
    ts_query = func.plainto_tsquery("russian", query)
    total = await self._fts_count(session, ts_query)
    if total == 0:
        return [], 0
    lessons = await self._fts_fetch(session, ts_query, page=page)
    return lessons, total

async def fts_search_all(self, session, query) -> list[LessonResult]:
    ts_query = func.plainto_tsquery("russian", query)
    return await self._fts_fetch(session, ts_query)
```

`_fts_count` / `_fts_fetch` drop the `abbr_conds` parameter. Sorting stays
`na_last, ts_rank DESC`.

`semantic_search`, `_build_level_results`, `search_by_level`,
`check_clarification` — unchanged.

## UX contract

L1 now returns 0 more often than before (no OR-fallback). The existing
empty-results handler in the Telegram and MAX bots already offers a
"расширенный поиск" button that invokes L2. No UX code changes needed.

## Tests

**Unit tests:** drop the OR-fallback and abbreviation scenarios from the
existing `fts_search` tests.

**New integration test** `tests/integration/test_search_golden.py`:

- Skipped unless `DATABASE_URL` is set (so CI without DB does not fail).
- Loads `examples.csv` (copied into `tests/fixtures/examples.csv`).
- For each of the 8 columns:
  - Runs `SearchService.fts_search(session, query)`.
  - Asserts result count is within ±30% of the expected column length.
  - Asserts at least one top-N result matches the expected column.
- For the 3 known L1-hard queries (`петр 1`, `2 закон ньютона`,
  `подготовка к ЕГЭ по физике`), also runs `search_by_level(level=2)` and
  asserts ≥5 relevant results appear (embedding-based recovery).

## Rollout order

1. Alembic migration `012` with trigger redefinition + backfill + downgrade.
2. `search.py` refactor.
3. Update existing unit tests.
4. Add integration golden-set test and CSV fixture.
5. Manual staging run: 8 queries, compare against the table.
6. Update `tasks/lessons.md` with the two structural limitations surfaced
   (digits vs roman/ordinal; user vocabulary vs content vocabulary).

## Risks

- **Subject rename** won't retro-reindex lessons. Mitigated by acceptance; a
  follow-up migration can add a `subjects` trigger if needed.
- **Larger `search_vector` payload** (descriptions can be ~500 chars). GIN
  indexes handle this well; no expected perf regression for a ~5k-row table.
- **Rank semantics shift:** items ranked high on title alone in the old
  system may now lose position to items that hit subject/grade in the
  weighted rank. Verified acceptable on golden set.
