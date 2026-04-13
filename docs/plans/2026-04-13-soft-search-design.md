# Soft Search — Design

**Date:** 2026-04-13
**Branch:** dev_2_levels
**Status:** Design approved, ready for implementation

## Problem

Current level-1 search uses PostgreSQL `plainto_tsquery('russian', ...)`, which is AND-logic over all tokens with no typo tolerance. As a result:

1. **Typos break search.** "теорма пифагра" → 0 results.
2. **Extra words break search.** "задачи на теорему пифагора 8 класс" → fewer results than "теорема пифагора" because every word must match.

Users fall through to the "Расширенный поиск (семантика)" button more often than they should. The goal is to soften level-1 matching so most organic queries succeed on the first pass, without changing the level-2 semantic flow.

## Approach

Replace `plainto_tsquery` with a combined, single-SQL search that unions two sources and ranks them on a shared score:

1. **FTS with OR + prefix** — `to_tsquery('russian', 'tok1:* | tok2:* | ...')` against the existing `search_vector`. Fixes the "extra words" problem and adds partial-stem matching.
2. **Trigram fallback via pg_trgm** — `similarity(title/description, query)` filtered by threshold. Fixes typos.

Results are de-duplicated by `lesson_id` and sorted by a unified score. Level-2 (semantic) remains unchanged, still triggered by the button when level-1 returns zero.

## Query pipeline

1. **Normalize.** Lowercase, strip punctuation, split into tokens, drop tokens shorter than 2 chars (keep digits — "7 класс" must work), sanitize tsquery special chars (`& | ! ( ) : *`).
2. **FTS (OR + prefix).** Build `tok1:* | tok2:* | ...`, run against `search_vector`, capture `ts_rank`.
3. **Trigram fallback.** `similarity(title, :q)` and `similarity(description, :q)`, filter rows where max > `trigram_similarity_threshold`.
4. **Union.** Merge on `lesson_id`; if a row is present in both sets, keep the FTS score (always higher by construction).
5. **Abbreviations.** `_abbr_filters` path is unchanged — merged into the result set as today.

All of the above runs as one SQL query using CTEs. No extra round-trips.

## Database changes

One Alembic migration:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX lessons_title_trgm_idx
    ON lessons USING GIN (title gin_trgm_ops);

CREATE INDEX lessons_description_trgm_idx
    ON lessons USING GIN (description gin_trgm_ops);
```

- GIN (not GIST) — read-heavy workload.
- No trigrams on `section`/`topic` — short strings, already covered by FTS; would bloat indexes.
- No generated `searchable_text` column — `similarity()` on each field + `GREATEST(...)` is enough; both indexes are usable.
- Down-migration drops indexes but **not** the extension.

**Pre-flight check:** verify `CREATE EXTENSION pg_trgm` is permitted on the production PostgreSQL (managed hosts sometimes need a ticket).

## Ranking

All hits mapped into a single `[0, 1]` score:

- **FTS hit:** `score = 0.5 + 0.5 * LEAST(ts_rank, 1.0)` → `[0.5, 1.0]`.
- **Trigram-only hit:** `score = GREATEST(similarity(title, q), similarity(description, q) * 0.7)` → `[0, ~0.5]`.
- **Both sources:** keep the FTS score (higher by construction).

Tie-breakers (preserved from current behavior):
1. `score DESC`
2. `url != 'N/A'` (real links first)
3. `lesson_id ASC` (stable sort)

## Config

New entries in `src/config.py`:

```
trigram_similarity_threshold: 0.3    # filter for trigram fallback
trigram_title_weight: 1.0
trigram_description_weight: 0.7
fts_score_floor: 0.5                 # minimum score for any FTS hit
enable_fuzzy_search: True            # safety flag — False falls back to plainto_tsquery
```

Unchanged:
- `semantic_similarity_threshold: 0.75` — level 2 untouched.
- `search_clarify_threshold: 10` — clarifying-button logic untouched; it will fire more often as a natural consequence of looser matching (this is desired).
- `results_per_page: 5`.

## Edge cases

- **Queries of 1–2 chars** → return empty without hitting the DB.
- **Digit-only tokens** ("8", "7 класс") → go through FTS only; skipped in the trigram pass (too many false positives).
- **Mixed cyrillic/latin / transliteration** → out of scope for this iteration.
- **Empty level-1 result** → same button ("Расширенный поиск (семантика)"), same handler, just appearing less often.
- **Clarification** → `check_clarification` will more often suggest subject/grade/topic refinement. That's the intended UX on a larger, noisier result set.

## Performance

One SQL with two CTEs. Both paths use GIN indexes (`search_vector` + two trigram indexes). On the current scale (under ~50k lessons), expected latency is single-digit milliseconds. No caching needed.

## Testing

**Unit (`search_service`):**
- Query with a typo → found via trigram path.
- Query with extra words → found via OR path.
- Exact match → FTS hit ranks above any trigram hit.
- Empty / 1-char query → empty result, no exception.

**Integration:** docker-compose PostgreSQL with pg_trgm enabled; run the query through the real service.

**Manual:** 10–15 real queries that currently fail (collect from logs or from the product owner), verify each now succeeds at level 1.

## Rollback

`enable_fuzzy_search: False` in config → service falls back to the current `plainto_tsquery` path. Indexes stay in place (no cost). Use this as the first-release safety net; remove the flag after a week of clean metrics.

## Out of scope

- Transliteration (latin ↔ cyrillic).
- Lowering `semantic_similarity_threshold` or merging semantic into level 1.
- Query expansion via synonyms / thesaurus.
- Learning-to-rank from user clicks.

Each is tracked as a potential future iteration if post-release telemetry shows the need.
