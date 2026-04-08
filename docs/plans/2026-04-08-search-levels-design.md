# Search Levels Design

**Date:** 2026-04-08
**Status:** Validated

## Summary

Replace automatic AND→OR→semantic cascade with explicit 3-level search that the user controls via "Расширить поиск" button. Each level accumulates results from all previous levels.

## Levels

| Level | Results | Triggered by |
|-------|---------|--------------|
| 1 | AND FTS | Any text message (default) |
| 2 | AND FTS + Semantic | "Расширить поиск" button |
| 3 | AND FTS + Semantic + OR FTS | "Расширить поиск" button again |

Results are deduplicated across levels (no duplicate lessons).
"Расширить поиск" button is not shown at level 3.

## SearchService Changes

Replace `hybrid_search` with `search_by_level(session, query, level, page)`:
- **level 1**: AND FTS (`fts_search` with default AND)
- **level 2**: AND FTS + semantic (exclude AND ids from semantic)
- **level 3**: AND FTS + semantic + OR FTS (exclude AND+semantic ids from OR)

`fts_search_all` stays AND-only — used for clarification analysis at level 1.
At levels 2-3, clarification runs on the full accumulated result list directly.

## State (FSM)

| Key | Type | Description |
|-----|------|-------------|
| `search_query` | str | Current query (existing) |
| `search_level` | int | Current level: 1, 2, or 3 (new) |
| `search_all_lessons` | list | All results at current level (replaces `search_results`) |
| `search_filtered` | list | Filtered results after clarification (existing) |

## Callbacks

| Callback | Handler | Action |
|----------|---------|--------|
| `search:expand` | New handler | Read `search_query` + `search_level` from state, increment level, run `search_by_level` |
| `search:page:{n}` | Existing | Unchanged |
| `clarify:{level}:{idx}` | Existing | Unchanged |

## Keyboards

`search_pagination_keyboard(page, total_pages, level)` — adds `level` param:

```
◀ {page}/{total} ▶
🔍 Расширить поиск   ← only if level < 3, callback: search:expand
🔄 Новый поиск
```

## Scope

Changes apply to both **Telegram** (`src/telegram/`) and **MAX** (`src/max/`) bots symmetrically.

Files touched:
- `src/core/services/search.py` — `search_by_level`, remove `hybrid_search`
- `src/telegram/keyboards.py` — `search_pagination_keyboard` gets `level` param
- `src/telegram/handlers/search.py` — use `search_by_level`, new `search:expand` handler
- `src/max/keyboards.py` — same as Telegram keyboards
- `src/max/handlers/search.py` — same as Telegram handlers
- `tests/test_search.py` — update tests
