# Free-text search: back-to-clarification from final results

Date: 2026-04-13
Branch: dev_2_levels

## Problem

In the free-text search branch, after drilling through subject/grade
clarifications to the final list of lessons, the only action available is
"🔄 Новый поиск". There is no way to step back into the previous
clarification screen to try a different subject or grade without starting
the whole query over.

## Goal

From the final results screen, allow the user to return to the most
recent clarification step (one step back), staying consistent with the
existing `clarify:back` flow on intermediate clarification screens.

## Design decisions

1. **Back depth: one step.** A single button returns to the last
   clarification level. The user can press "◀ Назад" again on that
   screen to keep walking up the `clarify_history` stack. No direct
   shortcut to "root" — it would duplicate behavior already reachable in
   1–2 taps.

2. **Visibility: only when history is non-empty.** If the query landed
   on a final screen without any clarifications (`clarify_history == []`),
   the button is hidden. No "dead" controls.

3. **Dynamic label.** To avoid collision with the pagination "◀ Назад"
   button, the new button is labeled by the level of the last
   clarification step:
   - `subject` → "◀ К выбору предмета"
   - `grade`   → "◀ К выбору класса"
   - fallback  → "◀ К уточнению"

4. **Reuse existing callback.** The button emits `clarify:back`. The
   existing `handle_clarify_back` handler already pops the last history
   entry and restores the previous clarification screen — no new handler
   needed.

## Code changes

### `src/telegram/keyboards.py`

Extend `search_pagination_keyboard` with an optional parameter that
indicates the last clarification level (or `None` if history is empty):

```python
def search_pagination_keyboard(
    page: int,
    total_pages: int,
    level: int = 1,
    back_to_clarify: str | None = None,  # "subject" | "grade" | None
) -> InlineKeyboardMarkup
```

Button order in the keyboard:

1. pagination row (if `total_pages > 1`)
2. "🔍 Расширить поиск" (if `level < 2`)
3. **new back-to-clarify button** (if `back_to_clarify` is not `None`)
4. "🔄 Новый поиск"

Label mapping:

```python
_BACK_LABELS = {
    "subject": "◀ К выбору предмета",
    "grade":   "◀ К выбору класса",
}
# fallback: "◀ К уточнению"
```

Callback data: `clarify:back` (reuse existing).

### `src/telegram/handlers/search.py`

Helper to avoid duplicating the "what was the last clarification level"
computation:

```python
def _last_clarify_level(history: list[dict]) -> str | None:
    if not history:
        return None
    return (history[-1].get("clarify_result") or {}).get("level")
```

Call sites that build `search_pagination_keyboard` for the final results
screen pass `back_to_clarify=_last_clarify_level(history)`:

1. `handle_clarification` when `next_clarification is None`
   (search.py:245) — `history` is the local variable that was just
   augmented with the current state.
2. `paginate_search` (search.py:268, 278) — read `history` from
   `state.get_data()`.
3. `_run_search` (search.py:127) — after a fresh query
   `clarify_history == []`, so `back_to_clarify` resolves to `None` and
   the button is hidden. Correct.
4. `handle_clarify_back` fallback branch (search.py:182) — history is
   empty there, resolves to `None`. Correct.

## Edge cases

- **Pagination + back.** User on page 3 of final results presses the
  back button → `clarify:back` restores the clarification screen. No
  page-state leakage across clarifications (the next selection runs a
  fresh filter starting on page 1).
- **`choice == "all"` selection.** `handle_clarification` pushes to
  history before filtering regardless of the `all` branch
  (search.py:202-206), so back works identically.
- **Level expansion (1 → 2).** `_run_search` resets
  `clarify_history = []` on expansion. If a final screen shows up
  directly on level 2 with no clarifications, the back button is hidden.
  There is no level-2→level-1 back path by design — "🔄 Новый поиск"
  serves that purpose.
- **Chained back.** subject → grade → final → "К выбору класса"
  → intermediate "◀ Назад" → subject screen. Works out of the box from
  existing `handle_clarify_back` behavior.
- **Empty level-2 results screen** (`format_empty_level_2_results`). Only
  reachable from `_run_search` where history is empty. Out of scope —
  task is about "final results with links".

## Manual verification

- Query that triggers both subject and grade clarifications → final
  screen shows "◀ К выбору класса"; pressing it returns to grade screen;
  choosing a different grade yields a new final screen.
- Query with only a subject clarification → final screen shows "◀ К
  выбору предмета".
- Query with no clarifications → no back button, only pagination + new
  search.
- Paginate to page 2+, then press back → returns to clarification.
- After returning, pick a different subject/grade → new final screen is
  correct.
