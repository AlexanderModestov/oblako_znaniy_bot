# Search Clarification — Design

## Overview

When a search returns more results than a configurable threshold, the bot asks a clarifying question before showing results. This narrows down results in up to two steps: by subject, then by topic.

## User Flow

1. User enters search query
2. `hybrid_search` returns results
3. If results <= `SEARCH_CLARIFY_THRESHOLD` — show as usual
4. If results > threshold and multiple subjects — ask: "Найдено N результатов. Показать уроки по {доминирующий предмет}? Или все найденные?" (2 кнопки)
5. If user picks subject and filtered results > threshold and multiple topics — ask: "Найдено N результатов по {предмет}. Показать уроки по теме {тема}? Или все по {предмет}?" (2 кнопки)
6. After second clarification (or if values are uniform) — show results with pagination

"Dominant" = the subject/topic with the most results.

## Interfaces

Telegram + Max bots. Not web app.

## Architecture

### Config (`src/config.py`)

New setting:
- `search_clarify_threshold: int` from env `SEARCH_CLARIFY_THRESHOLD`

### Core Layer (`src/core/`)

**`schemas.py`** — new model:
```python
class ClarifyQuestion(BaseModel):
    stage: str              # "subject" or "topic"
    dominant_value: str     # e.g. "Математика"
    total: int              # total results count
    message: str            # question text for user
```

**`services/search.py`** — new method:
```python
def check_clarification(
    self,
    lessons: list[LessonResult],
    stage: str = "subject",
    selected_subject: str | None = None
) -> ClarifyQuestion | None
```

Logic:
1. If `len(lessons) <= threshold` → `None`
2. Group by field (`subject` for stage "subject", `topic` for stage "topic")
3. If all values are the same → `None`
4. Find dominant value (max count)
5. Return `ClarifyQuestion` with generated message text

Message templates:
- Subject stage: `"Найдено {total} результатов. Показать уроки по {value}? Или все найденные?"`
- Topic stage: `"Найдено {total} результатов по {subject}. Показать уроки по теме {value}? Или все по {subject}?"`

### Bot Layer (Telegram + Max)

**FSM State** additions:
- `search_results` — full results list (serialized)
- `clarify_stage` — current stage: `"subject"` or `"topic"`
- `clarify_subject` — selected subject (after first clarification)

**Callback data:**
- `clarify:dominant` — user picked dominant value
- `clarify:all` — user picked "all"

Values are not passed in callback data (Telegram 64-byte limit). Dominant value and context are read from FSM state.

**`keyboards.py`** — new function for clarification keyboard:
- Button 1: `"{dominant_value}"` → `clarify:dominant`
- Button 2: `"Все найденные"` → `clarify:all`

**`handlers/search.py`** — changes:
- After `hybrid_search`, call `check_clarification`. If returns question — show it with buttons, save results to FSM state
- New callback handler for `clarify:*` — filters saved results by subject/topic, runs `check_clarification` again for next stage or shows results

**Filtering is client-side** — no re-query to DB. Filter `SearchResult.lessons` list in memory.

## Example Scenario

1. User: "функции"
2. `hybrid_search` → 25 results
3. `check_clarification(lessons, "subject")` → dominant: Математика (18/25)
4. Bot: "Найдено 25 результатов. Показать уроки по Математике? Или все найденные?"
5. User taps "Математика"
6. Filter by subject → 18 results
7. `check_clarification(lessons, "topic", selected_subject="Математика")` → dominant: Квадратные функции (12/18)
8. Bot: "Найдено 18 результатов по Математике. Показать уроки по теме Квадратные функции? Или все по Математике?"
9. User picks → show with pagination
