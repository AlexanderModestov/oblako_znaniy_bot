# Search AND→OR Fallback Design

**Date:** 2026-04-07
**Status:** Validated

## Problem

Free-form search uses OR logic for multi-word queries, causing irrelevant results.
Example: "Петр 1" → `"Петр" OR "1"` → matches every lesson containing "1" (Вариант 1, Урок 1, etc.)

## Solution: Cascading Search

```
1. AND FTS (plainto_tsquery) → count results
2. results >= fts_min_results → use AND results (existing clarification logic applies)
3. results < fts_min_results → OR FTS + semantic (existing fallback behavior)
```

## Changes

### `_build_tsquery(query)` — AND logic (default)
Use `plainto_tsquery` for all queries. Remove the OR-joining for multi-word queries.

### `_build_tsquery_or(query)` — OR logic (fallback)
Preserve current OR behavior for use in the fallback path only.

### `hybrid_search`
1. Run AND FTS, get total count
2. If `total >= fts_min_results` → paginate and return AND results
3. If `total < fts_min_results` → run OR FTS + semantic (current logic, unchanged)

### `fts_search_all`
Switch to AND logic (used for clarification analysis — should be consistent with main search).

## No Changes
- Clarification logic (`check_clarification`)
- Semantic search
- Pagination
- `.env` config — reuses existing `fts_min_results`
