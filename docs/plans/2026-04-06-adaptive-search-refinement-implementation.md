# Adaptive Search Refinement — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace "dominant value" clarification with adaptive multi-level refinement showing all options as buttons, and add grade to search results.

**Architecture:** The `check_clarification` method returns a list of options (not a single dominant) with a `level` indicating what's diverse. Handlers use a unified `clarify:{level}:{index}` callback pattern. Filtering is always in-memory from cached results.

**Tech Stack:** Python, Pydantic, Aiogram (Telegram), maxapi (MAX), SQLAlchemy

---

### Task 1: Add `grade` to `LessonResult` schema

**Files:**
- Modify: `src/core/schemas.py:25-33`

**Step 1: Update the schema**

In `src/core/schemas.py`, add `grade` field to `LessonResult`:

```python
class LessonResult(BaseModel):
    title: str
    url: str
    description: str | None = None
    subject: str | None = None
    grade: int | None = None          # <-- NEW
    section: str | None = None
    topic: str | None = None
    is_semantic: bool = False
```

**Step 2: Verify no breakage**

Run: `python -m pytest tests/ -v`
Expected: All existing tests PASS (grade defaults to None)

**Step 3: Commit**

```bash
git add src/core/schemas.py
git commit -m "feat: add grade field to LessonResult schema"
```

---

### Task 2: Replace `ClarifyQuestion` with `ClarifyOptions`

**Files:**
- Modify: `src/core/schemas.py:47-52`

**Step 1: Replace the schema**

Replace `ClarifyQuestion` in `src/core/schemas.py` with:

```python
class ClarifyOption(BaseModel):
    value: str          # e.g. "Математика", "5", "Тема 1: Функции"
    display: str        # button text, e.g. "Математика (15)"
    count: int          # number of results


class ClarifyResult(BaseModel):
    level: str          # "subject", "grade", or "topic"
    options: list[ClarifyOption]
    message: str        # question text for user
    total: int          # total results count
```

**Step 2: Remove old import references**

Search for `ClarifyQuestion` in the codebase and update imports:
- `src/core/services/search.py:10` — change to `ClarifyOption, ClarifyResult`
- `tests/test_search.py:3` — change to `ClarifyOption, ClarifyResult`

Don't fix test logic yet — just imports. Tests will fail; that's expected.

**Step 3: Commit**

```bash
git add src/core/schemas.py src/core/services/search.py tests/test_search.py
git commit -m "feat: replace ClarifyQuestion with ClarifyResult schema"
```

---

### Task 3: Rewrite `check_clarification` in search service

**Files:**
- Modify: `src/core/services/search.py:125-157`

**Step 1: Write failing tests**

Replace the clarification tests in `tests/test_search.py` (lines 46-95) with:

```python
def _make_lesson(subject="Математика", grade=5, topic="Функции", section="Раздел 1"):
    return LessonResult(
        title="Урок", url="https://example.com",
        subject=subject, grade=grade, section=section, topic=topic,
    )


@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
def test_clarify_below_threshold_returns_none(mock_settings):
    service = SearchService()
    lessons = [_make_lesson() for _ in range(5)]
    assert service.check_clarification(lessons) is None


@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
def test_clarify_single_subject_single_grade_returns_none(mock_settings):
    service = SearchService()
    lessons = [_make_lesson(subject="Математика", grade=5) for _ in range(15)]
    assert service.check_clarification(lessons) is None


@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
def test_clarify_multiple_subjects(mock_settings):
    service = SearchService()
    lessons = (
        [_make_lesson(subject="Математика") for _ in range(10)]
        + [_make_lesson(subject="Физика") for _ in range(5)]
    )
    result = service.check_clarification(lessons)
    assert result is not None
    assert result.level == "subject"
    assert len(result.options) == 2
    assert result.options[0].value == "Математика"
    assert result.options[0].count == 10
    assert result.options[1].value == "Физика"
    assert result.options[1].count == 5
    assert result.total == 15


@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
def test_clarify_single_subject_multiple_grades(mock_settings):
    service = SearchService()
    lessons = (
        [_make_lesson(subject="Математика", grade=5) for _ in range(8)]
        + [_make_lesson(subject="Математика", grade=6) for _ in range(7)]
    )
    result = service.check_clarification(lessons)
    assert result is not None
    assert result.level == "grade"
    assert len(result.options) == 2
    assert result.options[0].value == "5"
    assert result.options[0].count == 8


@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
def test_clarify_single_subject_single_grade_multiple_topics(mock_settings):
    service = SearchService()
    lessons = (
        [_make_lesson(subject="Математика", grade=5, topic="Функции") for _ in range(7)]
        + [_make_lesson(subject="Математика", grade=5, topic="Уравнения") for _ in range(6)]
    )
    result = service.check_clarification(lessons)
    assert result is not None
    assert result.level == "topic"
    assert len(result.options) == 2


@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
def test_clarify_options_sorted_by_count_desc(mock_settings):
    service = SearchService()
    lessons = (
        [_make_lesson(subject="Физика") for _ in range(3)]
        + [_make_lesson(subject="Математика") for _ in range(9)]
        + [_make_lesson(subject="Химия") for _ in range(2)]
    )
    result = service.check_clarification(lessons)
    assert result.options[0].value == "Математика"
    assert result.options[1].value == "Физика"
    assert result.options[2].value == "Химия"


@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
def test_clarify_max_7_options(mock_settings):
    """More than 7 unique subjects → only top 7 shown."""
    service = SearchService()
    subjects = [f"Предмет_{i}" for i in range(9)]
    lessons = []
    for i, subj in enumerate(subjects):
        lessons.extend([_make_lesson(subject=subj) for _ in range(10 - i)])
    result = service.check_clarification(lessons)
    assert len(result.options) <= 7
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_search.py -v`
Expected: FAIL — `check_clarification` has wrong signature/return type

**Step 3: Rewrite `check_clarification`**

Replace `check_clarification` method (lines 125-157) in `src/core/services/search.py`:

```python
    def check_clarification(
        self,
        lessons: list[LessonResult],
    ) -> ClarifyResult | None:
        """Analyze results and return adaptive clarification if needed.

        Priority: subjects → grades → topics.
        Returns None if below threshold or results are homogeneous.
        """
        if len(lessons) <= self.clarify_threshold:
            return None

        # Try each level in priority order
        for level, field, fmt in [
            ("subject", "subject", lambda v, c: f"{v} ({c})"),
            ("grade", "grade", lambda v, c: f"{v} класс ({c})"),
            ("topic", "topic", lambda v, c: f"{v} ({c})"),
        ]:
            counts: dict[str, int] = {}
            for lesson in lessons:
                value = getattr(lesson, field)
                if value is None:
                    continue
                key = str(value)
                counts[key] = counts.get(key, 0) + 1

            if len(counts) <= 1:
                continue

            # Sort by count descending, cap at 7
            sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:7]
            options = [
                ClarifyOption(value=val, display=fmt(val, cnt), count=cnt)
                for val, cnt in sorted_items
            ]

            total = len(lessons)
            if level == "subject":
                message = f"Найдено {total} результатов. Выберите предмет:"
            elif level == "grade":
                subj = lessons[0].subject or ""
                message = f"Найдено {total} результатов по {subj}. Выберите класс:"
            else:
                subj = lessons[0].subject or ""
                grade = lessons[0].grade
                grade_str = f", {grade} класс" if grade else ""
                message = f"Найдено {total} результатов — {subj}{grade_str}. Выберите тему:"

            return ClarifyResult(level=level, options=options, message=message, total=total)

        return None
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_search.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/core/services/search.py tests/test_search.py
git commit -m "feat: rewrite check_clarification with adaptive multi-level logic"
```

---

### Task 4: Include `grade` in search results (service layer)

**Files:**
- Modify: `src/core/services/search.py:49-58, 88-97, 170-179`

**Step 1: Add `grade=l.grade` to all three places where `LessonResult` is constructed**

In `fts_search` (line 50-58):
```python
            LessonResult(
                title=l.title, url=l.url,
                description=l.description,
                subject=l.subject.name,
                grade=l.grade,
                section=l.section,
                topic=l.topic,
                is_semantic=False,
            )
```

In `semantic_search` (line 88-97) — same pattern, add `grade=lesson.grade`.

In `fts_search_all` (line 170-179) — same pattern, add `grade=l.grade`.

**Step 2: Run tests**

Run: `python -m pytest tests/ -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add src/core/services/search.py
git commit -m "feat: include grade in LessonResult from search queries"
```

---

### Task 5: Add grade to formatters (both Telegram and MAX)

**Files:**
- Modify: `src/telegram/formatters.py:19-27`
- Modify: `src/max/formatters.py:19-27`

**Step 1: Update `format_lesson_text` in both files**

Replace line 21 in both `src/telegram/formatters.py` and `src/max/formatters.py`:

```python
# OLD:
    parts = [p for p in [lesson.subject, lesson.section, lesson.topic] if p]

# NEW:
    grade_str = f"{lesson.grade} класс" if lesson.grade else None
    parts = [p for p in [lesson.subject, grade_str, lesson.section, lesson.topic] if p]
```

**Step 2: Run tests**

Run: `python -m pytest tests/ -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add src/telegram/formatters.py src/max/formatters.py
git commit -m "feat: add grade to search result formatting"
```

---

### Task 6: New clarify keyboard (Telegram)

**Files:**
- Modify: `src/telegram/keyboards.py:124-128`

**Step 1: Rewrite `clarify_keyboard`**

Replace `clarify_keyboard` function (lines 124-128) in `src/telegram/keyboards.py`:

```python
def clarify_keyboard(options: list[dict], level: str) -> InlineKeyboardMarkup:
    """Build clarification keyboard from options.

    Each option: {"value": str, "display": str, "count": int}
    Callback: clarify:{level}:{index}
    """
    buttons = []
    for i, opt in enumerate(options):
        buttons.append([
            InlineKeyboardButton(text=opt["display"], callback_data=f"clarify:{level}:{i}")
        ])
    buttons.append([
        InlineKeyboardButton(text="Показать все", callback_data=f"clarify:{level}:all")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
```

**Step 2: Commit**

```bash
git add src/telegram/keyboards.py
git commit -m "feat: rewrite clarify_keyboard for multi-option layout"
```

---

### Task 7: New clarify keyboard (MAX)

**Files:**
- Modify: `src/max/keyboards.py:108-112`

**Step 1: Rewrite `clarify_keyboard`**

Replace `clarify_keyboard` function (lines 108-112) in `src/max/keyboards.py`:

```python
def clarify_keyboard(options: list[dict], level: str) -> InlineKeyboardBuilder:
    """Build clarification keyboard from options.

    Each option: {"value": str, "display": str, "count": int}
    Callback: clarify:{level}:{index}
    """
    kb = InlineKeyboardBuilder()
    for i, opt in enumerate(options):
        kb.row(CallbackButton(text=opt["display"], payload=f"clarify:{level}:{i}"))
    kb.row(CallbackButton(text="Показать все", payload=f"clarify:{level}:all"))
    return kb
```

**Step 2: Commit**

```bash
git add src/max/keyboards.py
git commit -m "feat: rewrite MAX clarify_keyboard for multi-option layout"
```

---

### Task 8: Rewrite Telegram search handler clarification flow

**Files:**
- Modify: `src/telegram/handlers/search.py:58-138`

**Step 1: Update imports**

In `src/telegram/handlers/search.py` line 12, change:
```python
# OLD:
from src.core.schemas import LessonResult, SearchResult

# NEW:
from src.core.schemas import ClarifyResult, LessonResult, SearchResult
```

**Step 2: Update `handle_search` clarification block (lines 62-75)**

Replace lines 58-75:

```python
    await state.update_data(search_query=query, search_filtered=None, clarify_stage=None)

    result = await search_service.hybrid_search(session, query, page=1)

    # Check if clarification might be needed
    if result.total > search_service.clarify_threshold:
        all_lessons = await search_service.fts_search_all(session, query)
        clarification = search_service.check_clarification(all_lessons)
        if clarification:
            await state.update_data(
                search_results=[l.model_dump() for l in all_lessons],
                search_total=result.total,
                clarify_result=clarification.model_dump(),
            )
            options = [o.model_dump() for o in clarification.options]
            keyboard = clarify_keyboard(options, clarification.level)
            await message.answer(clarification.message, reply_markup=keyboard)
            return
```

**Step 3: Rewrite `handle_clarification` callback (lines 84-138)**

Replace the entire `handle_clarification` function:

```python
@router.callback_query(F.data.startswith("clarify:"))
async def handle_clarification(callback: CallbackQuery, state: FSMContext, session):
    parts = callback.data.split(":")  # clarify:{level}:{index_or_all}
    level = parts[1]
    choice = parts[2]

    data = await state.get_data()
    all_lessons = [LessonResult(**l) for l in data.get("search_results", [])]
    query = data.get("search_query", "")
    clarify_data = data.get("clarify_result", {})

    if choice == "all":
        filtered = all_lessons
    else:
        idx = int(choice)
        options = clarify_data.get("options", [])
        selected_value = options[idx]["value"]

        field = level  # "subject", "grade", or "topic"
        filtered = [
            l for l in all_lessons
            if str(getattr(l, field) or "") == selected_value
        ]

    # Re-check for next-level clarification on filtered results
    next_clarification = search_service.check_clarification(filtered)
    if next_clarification:
        await state.update_data(
            search_results=[l.model_dump() for l in filtered],
            clarify_result=next_clarification.model_dump(),
        )
        options = [o.model_dump() for o in next_clarification.options]
        keyboard = clarify_keyboard(options, next_clarification.level)
        await callback.message.edit_text(next_clarification.message, reply_markup=keyboard)
        await callback.answer()
        return

    # Show results with pagination
    total = len(filtered)
    per_page = search_service.per_page
    page_lessons = filtered[:per_page]

    search_result = SearchResult(
        query=query, lessons=page_lessons,
        total=total, page=1, per_page=per_page,
    )
    text = format_text_results(search_result)

    await state.update_data(
        search_filtered=[l.model_dump() for l in filtered],
        clarify_result=None,
    )

    keyboard = None
    if search_result.total_pages > 0:
        keyboard = search_pagination_keyboard(1, search_result.total_pages)
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()
```

**Step 4: Commit**

```bash
git add src/telegram/handlers/search.py
git commit -m "feat: rewrite Telegram clarification handler for adaptive refinement"
```

---

### Task 9: Rewrite MAX search handler clarification flow

**Files:**
- Modify: `src/max/handlers/search.py:51-141`

**Step 1: Update imports**

In `src/max/handlers/search.py` line 7, change:
```python
# OLD:
from src.core.schemas import LessonResult, SearchResult

# NEW:
from src.core.schemas import ClarifyResult, LessonResult, SearchResult
```

**Step 2: Update `handle_search` clarification block (lines 56-68)**

Replace lines 51-68:

```python
    await context.update_data(search_query=query, search_filtered=None, clarify_stage=None)

    result = await search_service.hybrid_search(session, query, page=1)

    # Check if clarification might be needed
    if result.total > search_service.clarify_threshold:
        all_lessons = await search_service.fts_search_all(session, query)
        clarification = search_service.check_clarification(all_lessons)
        if clarification:
            await context.update_data(
                search_results=[l.model_dump() for l in all_lessons],
                search_total=result.total,
                clarify_result=clarification.model_dump(),
            )
            options = [o.model_dump() for o in clarification.options]
            kb = clarify_keyboard(options, clarification.level)
            await event.message.answer(clarification.message, attachments=[kb.as_markup()])
            return
```

**Step 3: Rewrite `handle_clarification` callback (lines 78-141)**

Replace the entire `handle_clarification` function:

```python
@router.message_callback(F.callback.payload.startswith("clarify:"))
async def handle_clarification(event: MessageCallback, context: MemoryContext, session: AsyncSession):
    parts = event.callback.payload.split(":")  # clarify:{level}:{index_or_all}
    level = parts[1]
    choice = parts[2]

    data = await context.get_data()
    all_lessons = [LessonResult(**l) for l in data.get("search_results", [])]
    query = data.get("search_query", "")
    clarify_data = data.get("clarify_result", {})

    if choice == "all":
        filtered = all_lessons
    else:
        idx = int(choice)
        options = clarify_data.get("options", [])
        selected_value = options[idx]["value"]

        field = level  # "subject", "grade", or "topic"
        filtered = [
            l for l in all_lessons
            if str(getattr(l, field) or "") == selected_value
        ]

    # Re-check for next-level clarification on filtered results
    next_clarification = search_service.check_clarification(filtered)
    if next_clarification:
        await context.update_data(
            search_results=[l.model_dump() for l in filtered],
            clarify_result=next_clarification.model_dump(),
        )
        options = [o.model_dump() for o in next_clarification.options]
        kb = clarify_keyboard(options, next_clarification.level)
        await event.bot.edit_message(
            message_id=event.message.body.mid,
            text=next_clarification.message,
            attachments=[kb.as_markup()],
        )
        return

    # Show results with pagination
    total = len(filtered)
    per_page = search_service.per_page
    page_lessons = filtered[:per_page]

    search_result = SearchResult(
        query=query, lessons=page_lessons,
        total=total, page=1, per_page=per_page,
    )
    text = format_text_results(search_result)

    await context.update_data(
        search_filtered=[l.model_dump() for l in filtered],
        clarify_result=None,
    )

    if search_result.total_pages > 0:
        kb = search_pagination_keyboard(1, search_result.total_pages)
        await event.bot.edit_message(
            message_id=event.message.body.mid,
            text=text,
            attachments=[kb.as_markup()],
        )
    else:
        await event.bot.edit_message(
            message_id=event.message.body.mid,
            text=text,
        )
```

**Step 4: Commit**

```bash
git add src/max/handlers/search.py
git commit -m "feat: rewrite MAX clarification handler for adaptive refinement"
```

---

### Task 10: Final verification

**Step 1: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All PASS

**Step 2: Verify no import errors**

Run: `python -c "from src.telegram.handlers.search import router; from src.max.handlers.search import router"`
Expected: No errors

**Step 3: Commit all remaining changes (if any)**

```bash
git status
```

---

## Summary of all changes

| File | What changes |
|------|-------------|
| `src/core/schemas.py` | Add `grade` to `LessonResult`; replace `ClarifyQuestion` → `ClarifyOption` + `ClarifyResult` |
| `src/core/services/search.py` | Add `grade` to all `LessonResult` constructors; rewrite `check_clarification` for adaptive logic |
| `src/telegram/formatters.py` | Add grade to context line |
| `src/max/formatters.py` | Add grade to context line |
| `src/telegram/keyboards.py` | Rewrite `clarify_keyboard` for multi-option buttons |
| `src/max/keyboards.py` | Rewrite `clarify_keyboard` for multi-option buttons |
| `src/telegram/handlers/search.py` | Unified `clarify:*` callback handler with re-check |
| `src/max/handlers/search.py` | Mirror Telegram handler changes |
| `tests/test_search.py` | New tests for adaptive clarification |
