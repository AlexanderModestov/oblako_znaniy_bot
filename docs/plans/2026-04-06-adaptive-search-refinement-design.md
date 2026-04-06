# Adaptive Search Refinement Design

**Date:** 2026-04-06
**Status:** Validated

## Summary

Replace the current "dominant subject" clarification logic with adaptive, multi-level refinement that shows all available options at each level and intelligently picks the narrowing criterion based on result diversity.

## Current Behavior

- Clarification triggers when results > 10 (hardcoded)
- Shows only the most common subject: "Показать по {dominant}? Или все?"
- Two fixed stages: subject → topic
- Grade (class) not used in clarification or result formatting

## New Behavior

### Adaptive Narrowing Logic

When search returns more than `search_clarify_threshold` results, analyze what's diverse:

1. **Different subjects?** → show buttons with ALL found subjects + "Показать все"
2. **One subject, different grades?** → show grade buttons + "Показать все по {subject}"
3. **One subject, one grade, different topics?** → show topic buttons + "Показать все"
4. **All homogeneous** → show results immediately

After user selects an option, filter results and re-check: if filtered results still exceed threshold and have diversity at the next level, offer another refinement. Otherwise, show results.

Filtering is always done on already-fetched results (no new search query).

### Configuration

`search_clarify_threshold` moved to `.env` variable (default: 10).

### Result Formatting

Add grade to the meta line:
```
1. Математика | 5 класс | Раздел 1 | Тема 1
   📚 Название урока
   → ссылка
```

If grade is None, omit it: `Математика | Раздел 1 | Тема 1`

### Message & Button Format

**Subject refinement:**
```
Найдено 25 результатов по запросу «дроби».
Выберите предмет:
```
Buttons:
```
[ Математика (15) ]
[ Физика (7) ]
[ Информатика (3) ]
[ Показать все (25) ]
```

**Grade refinement (after subject selected):**
```
Найдено 15 результатов по «дроби» в предмете Математика.
Выберите класс:
```
Buttons:
```
[ 5 класс (8) ]
[ 6 класс (7) ]
[ Показать все (15) ]
```

**Topic refinement:**
```
Найдено 8 результатов по «дроби» — Математика, 5 класс.
Выберите тему:
```
Buttons:
```
[ Тема 1: Обыкновенные дроби (5) ]
[ Тема 3: Десятичные дроби (3) ]
[ Показать все (8) ]
```

Count in parentheses shows number of results per option.

## Edge Cases

### Callback data length
Telegram limits callback_data to 64 bytes. Use index-based references: `clarify:topic:3` instead of full text.

### Too many options (>8 buttons)
Show top 7 by result count + "Показать все". Prevents screen clutter.

### Re-check threshold after filtering
If filtered results ≤ threshold → show immediately, skip further refinement. Prevents excessive question chains.

### Grade = None
- In formatting: omit grade from meta line
- In grade refinement buttons: group as "Без класса" if such lessons exist

## Files to Change

| File | Change |
|------|--------|
| `src/config.py` | `search_clarify_threshold` from `.env` |
| `src/core/services/search.py` | Rewrite `check_clarification` → adaptive multi-level logic returning `{ level, options, message }` |
| `src/telegram/keyboards.py` | Dynamic inline keyboard from options list + "Показать все" |
| `src/telegram/handlers/search.py` | Unified `clarify:*` callback handler, re-check after filter |
| `src/telegram/formatters.py` | Add grade to meta line |
| `src/max/handlers/search.py` | Mirror changes for MAX bot |
