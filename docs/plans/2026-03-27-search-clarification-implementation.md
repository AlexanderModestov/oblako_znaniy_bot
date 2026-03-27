# Search Clarification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** When search results exceed a threshold, ask the user a clarifying question to narrow by dominant subject, then by dominant topic.

**Architecture:** New `ClarifyQuestion` schema + `check_clarification` method in core. Telegram and Max handlers save full results to FSM state, show clarification keyboard, and filter on user choice. No DB re-queries — filtering is in-memory.

**Tech Stack:** Python, pydantic, aiogram (Telegram), maxapi (Max)

---

### Task 1: Add `search_clarify_threshold` to config

**Files:**
- Modify: `src/config.py:19-21`

**Step 1: Add setting**

In `src/config.py`, after line 21 (`results_per_page: int = 5`), add:

```python
    search_clarify_threshold: int = 10
```

**Step 2: Verify**

Run: `python -c "from src.config import Settings; print(Settings.model_fields.keys())"` or check import works.

**Step 3: Commit**

```bash
git add src/config.py
git commit -m "feat: add search_clarify_threshold config setting"
```

---

### Task 2: Add `ClarifyQuestion` schema

**Files:**
- Modify: `src/core/schemas.py:1-51`

**Step 1: Write the test**

In `tests/test_schemas.py`, add:

```python
from src.core.schemas import ClarifyQuestion

def test_clarify_question_schema():
    q = ClarifyQuestion(
        stage="subject",
        dominant_value="Математика",
        total=25,
        message="Найдено 25 результатов. Показать уроки по Математике? Или все найденные?",
    )
    assert q.stage == "subject"
    assert q.dominant_value == "Математика"
    assert q.total == 25
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_schemas.py::test_clarify_question_schema -v`
Expected: FAIL — `ClarifyQuestion` not defined.

**Step 3: Add schema to `src/core/schemas.py`**

After `SearchResult` class (after line 43), add:

```python
class ClarifyQuestion(BaseModel):
    stage: str              # "subject" or "topic"
    dominant_value: str     # e.g. "Математика"
    total: int              # total results count
    message: str            # question text for user
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_schemas.py::test_clarify_question_schema -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/core/schemas.py tests/test_schemas.py
git commit -m "feat: add ClarifyQuestion schema"
```

---

### Task 3: Implement `check_clarification` in SearchService

**Files:**
- Modify: `src/core/services/search.py:22-29`
- Modify: `tests/test_search.py`

**Step 1: Write tests**

Add to `tests/test_search.py`:

```python
from src.core.schemas import LessonResult, ClarifyQuestion

def _make_lesson(subject="Математика", topic="Функции"):
    return LessonResult(
        title="Урок", url="https://example.com",
        subject=subject, topic=topic,
    )

@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
def test_check_clarification_below_threshold(mock_settings):
    """No clarification if results <= threshold."""
    service = SearchService()
    lessons = [_make_lesson() for _ in range(5)]
    result = service.check_clarification(lessons, stage="subject")
    assert result is None

@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
def test_check_clarification_single_subject(mock_settings):
    """No clarification if all results have same subject."""
    service = SearchService()
    lessons = [_make_lesson(subject="Математика") for _ in range(15)]
    result = service.check_clarification(lessons, stage="subject")
    assert result is None

@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
def test_check_clarification_subject_stage(mock_settings):
    """Clarification returned with dominant subject."""
    service = SearchService()
    lessons = (
        [_make_lesson(subject="Математика") for _ in range(10)]
        + [_make_lesson(subject="Физика") for _ in range(5)]
    )
    result = service.check_clarification(lessons, stage="subject")
    assert result is not None
    assert result.stage == "subject"
    assert result.dominant_value == "Математика"
    assert result.total == 15

@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
def test_check_clarification_topic_stage(mock_settings):
    """Topic stage clarification with selected_subject context."""
    service = SearchService()
    lessons = (
        [_make_lesson(topic="Функции") for _ in range(8)]
        + [_make_lesson(topic="Уравнения") for _ in range(4)]
    )
    result = service.check_clarification(
        lessons, stage="topic", selected_subject="Математика",
    )
    assert result is not None
    assert result.stage == "topic"
    assert result.dominant_value == "Функции"
    assert "Математике" not in result.message or "Математика" in result.message
```

Update `_make_mock_settings` to include `search_clarify_threshold`:

```python
def _make_mock_settings():
    settings = MagicMock()
    settings.fts_min_results = 3
    settings.semantic_similarity_threshold = 0.75
    settings.results_per_page = 5
    settings.search_clarify_threshold = 10
    settings.openai_api_key = "test-key"
    return settings
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_search.py -v -k "clarification"`
Expected: FAIL — `check_clarification` not defined.

**Step 3: Implement `check_clarification`**

In `src/core/services/search.py`, add to `SearchService.__init__`:

```python
self.clarify_threshold = settings.search_clarify_threshold
```

Add new method to `SearchService`:

```python
def check_clarification(
    self,
    lessons: list[LessonResult],
    stage: str = "subject",
    selected_subject: str | None = None,
) -> ClarifyQuestion | None:
    if len(lessons) <= self.clarify_threshold:
        return None

    field = "subject" if stage == "subject" else "topic"
    counts: dict[str, int] = {}
    for lesson in lessons:
        value = getattr(lesson, field) or ""
        if value:
            counts[value] = counts.get(value, 0) + 1

    if len(counts) <= 1:
        return None

    dominant = max(counts, key=counts.get)
    total = len(lessons)

    if stage == "subject":
        message = f"Найдено {total} результатов. Показать уроки по {dominant}? Или все найденные?"
    else:
        message = f"Найдено {total} результатов по {selected_subject}. Показать уроки по теме {dominant}? Или все по {selected_subject}?"

    return ClarifyQuestion(
        stage=stage,
        dominant_value=dominant,
        total=total,
        message=message,
    )
```

Update import at top of `search.py`:

```python
from src.core.schemas import ClarifyQuestion, LessonResult, SearchResult
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_search.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/core/services/search.py tests/test_search.py
git commit -m "feat: add check_clarification method to SearchService"
```

---

### Task 4: Add clarification keyboard to Telegram

**Files:**
- Modify: `src/telegram/keyboards.py:109-121`

**Step 1: Add `clarify_keyboard` function**

After `search_pagination_keyboard` in `src/telegram/keyboards.py`, add:

```python
def clarify_keyboard(dominant_value: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=dominant_value, callback_data="clarify:dominant")],
        [InlineKeyboardButton(text="Все найденные", callback_data="clarify:all")],
    ])
```

**Step 2: Commit**

```bash
git add src/telegram/keyboards.py
git commit -m "feat: add clarify_keyboard to Telegram keyboards"
```

---

### Task 5: Add clarification keyboard to Max

**Files:**
- Modify: `src/max/keyboards.py:95-105`

**Step 1: Add `clarify_keyboard` function**

After `search_pagination_keyboard` in `src/max/keyboards.py`, add:

```python
def clarify_keyboard(dominant_value: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text=dominant_value, payload="clarify:dominant"))
    kb.row(CallbackButton(text="Все найденные", payload="clarify:all"))
    return kb
```

**Step 2: Commit**

```bash
git add src/max/keyboards.py
git commit -m "feat: add clarify_keyboard to Max keyboards"
```

---

### Task 6: Update Telegram search handler with clarification flow

**Files:**
- Modify: `src/telegram/handlers/search.py`

**Step 1: Update imports**

Replace imports at top:

```python
from src.telegram.keyboards import clarify_keyboard, search_pagination_keyboard
```

**Step 2: Update `handle_search` to check for clarification**

Replace lines 50-59 of `handle_search` with:

```python
    await state.update_data(search_query=query)

    result = await search_service.hybrid_search(session, query, page=1)

    # Check if clarification is needed
    clarification = search_service.check_clarification(result.lessons, stage="subject")
    if clarification and result.total > search_service.clarify_threshold:
        # Save all results and clarification context to state
        await state.update_data(
            search_results=[l.model_dump() for l in result.lessons],
            search_total=result.total,
            clarify_stage="subject",
            clarify_dominant=clarification.dominant_value,
        )
        keyboard = clarify_keyboard(clarification.dominant_value)
        await message.answer(clarification.message, reply_markup=keyboard)
        return

    text = format_text_results(result)
    keyboard = None
    if result.total_pages > 0:
        keyboard = search_pagination_keyboard(1, result.total_pages)
    await message.answer(text, reply_markup=keyboard)
```

**Note:** For clarification we need ALL results, not just one page. We must modify `hybrid_search` call to get all results or get total lessons list. Since FTS paginates server-side, we need to fetch all FTS results when clarification might apply.

**Important detail:** The current `hybrid_search` only returns one page of results. For clarification we need to analyze ALL results to count subjects/topics. Two approaches:

**Approach A (simpler):** Add a new method `hybrid_search_all` that fetches all results without pagination — use only when total > threshold.

**Approach B (chosen — minimal change):** Use the `total` from `hybrid_search` to decide if clarification is needed, then fetch all results only if threshold is exceeded. Add parameter `fetch_all=False` to `hybrid_search`.

Actually, the simplest approach: `hybrid_search` already returns `total`. If `total > threshold`, we do a second query fetching all lessons (no pagination) to analyze subjects. Let's add `search_all` method.

**Revised Step 2: Add `fts_search_all` to SearchService**

In `src/core/services/search.py`, add method to `SearchService`:

```python
async def fts_search_all(self, session: AsyncSession, query: str) -> list[LessonResult]:
    """Fetch all FTS results without pagination (for clarification analysis)."""
    ts_query = _build_tsquery(query)
    na_last = case((Lesson.url == "N/A", 1), else_=0)
    q = (
        select(Lesson)
        .options(joinedload(Lesson.subject))
        .where(Lesson.search_vector.op("@@")(ts_query))
        .order_by(na_last, func.ts_rank(Lesson.search_vector, ts_query).desc())
    )
    result = await session.execute(q)
    return [
        LessonResult(
            title=l.title, url=l.url,
            description=l.description,
            subject=l.subject.name,
            section=l.section,
            topic=l.topic,
            is_semantic=False,
        )
        for l in result.scalars().unique().all()
    ]
```

**Revised handler logic:**

```python
    await state.update_data(search_query=query)

    result = await search_service.hybrid_search(session, query, page=1)

    # Check if clarification might be needed
    if result.total > search_service.clarify_threshold:
        all_lessons = await search_service.fts_search_all(session, query)
        clarification = search_service.check_clarification(all_lessons, stage="subject")
        if clarification:
            await state.update_data(
                search_results=[l.model_dump() for l in all_lessons],
                search_total=result.total,
                clarify_stage="subject",
                clarify_dominant=clarification.dominant_value,
            )
            keyboard = clarify_keyboard(clarification.dominant_value)
            await message.answer(clarification.message, reply_markup=keyboard)
            return

    text = format_text_results(result)
    keyboard = None
    if result.total_pages > 0:
        keyboard = search_pagination_keyboard(1, result.total_pages)
    await message.answer(text, reply_markup=keyboard)
```

**Step 3: Add clarification callback handler**

Add to `src/telegram/handlers/search.py`:

```python
@router.callback_query(F.data.startswith("clarify:"))
async def handle_clarification(callback: CallbackQuery, state: FSMContext, session):
    choice = callback.data.split(":")[1]  # "dominant" or "all"
    data = await state.get_data()

    all_lessons = [LessonResult(**l) for l in data.get("search_results", [])]
    query = data.get("search_query", "")
    stage = data.get("clarify_stage", "subject")
    dominant = data.get("clarify_dominant", "")

    if choice == "dominant":
        # Filter by dominant value
        field = "subject" if stage == "subject" else "topic"
        filtered = [l for l in all_lessons if getattr(l, field) == dominant]
    else:
        filtered = all_lessons

    # Check for second-level clarification (topic) if we just filtered by subject
    if choice == "dominant" and stage == "subject":
        clarification = search_service.check_clarification(
            filtered, stage="topic", selected_subject=dominant,
        )
        if clarification:
            await state.update_data(
                search_results=[l.model_dump() for l in filtered],
                clarify_stage="topic",
                clarify_dominant=clarification.dominant_value,
                clarify_subject=dominant,
            )
            keyboard = clarify_keyboard(clarification.dominant_value)
            await callback.message.edit_text(clarification.message, reply_markup=keyboard)
            await callback.answer()
            return

    # Show results with pagination
    total = len(filtered)
    per_page = search_service.per_page
    page_lessons = filtered[:per_page]

    result = SearchResult(
        query=query, lessons=page_lessons,
        total=total, page=1, per_page=per_page,
    )
    text = format_text_results(result)

    # Save filtered results for pagination
    await state.update_data(
        search_filtered=[l.model_dump() for l in filtered],
        clarify_stage=None,
    )

    keyboard = None
    if result.total_pages > 0:
        keyboard = search_pagination_keyboard(1, result.total_pages)
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()
```

**Step 4: Update pagination handler to support filtered results**

Update `paginate_search` in `src/telegram/handlers/search.py`:

```python
@router.callback_query(F.data.startswith("search:page:"))
async def paginate_search(callback: CallbackQuery, state: FSMContext, session):
    page = int(callback.data.split(":")[-1])
    data = await state.get_data()
    query = data.get("search_query", "")

    # Check if we have filtered results from clarification
    filtered_data = data.get("search_filtered")
    if filtered_data:
        filtered = [LessonResult(**l) for l in filtered_data]
        per_page = search_service.per_page
        offset = (page - 1) * per_page
        page_lessons = filtered[offset : offset + per_page]
        result = SearchResult(
            query=query, lessons=page_lessons,
            total=len(filtered), page=page, per_page=per_page,
        )
    else:
        result = await search_service.hybrid_search(session, query, page=page)

    text = format_text_results(result)
    keyboard = search_pagination_keyboard(page, result.total_pages)
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()
```

**Step 5: Update import for LessonResult and SearchResult**

```python
from src.core.schemas import LessonResult, SearchResult
```

**Step 6: Clear filtered state on new search**

In `handle_search`, after `await state.update_data(search_query=query)`, add:

```python
    await state.update_data(search_filtered=None, clarify_stage=None)
```

**Step 7: Commit**

```bash
git add src/core/services/search.py src/telegram/handlers/search.py
git commit -m "feat: add clarification flow to Telegram search handler"
```

---

### Task 7: Update Max search handler with clarification flow

**Files:**
- Modify: `src/max/handlers/search.py`

**Step 1: Mirror Telegram changes for Max**

Apply the same logic as Task 6 but using Max API:
- `event.message.answer(text, attachments=[kb.as_markup()])` instead of `message.answer(text, reply_markup=keyboard)`
- `context` instead of `state` for FSM
- `event.callback.payload` instead of `callback.data`
- `event.bot.edit_message(message_id=event.message.body.mid, ...)` instead of `callback.message.edit_text(...)`

Full updated `src/max/handlers/search.py`:

```python
from maxapi import F, Router
from maxapi.context import MemoryContext
from maxapi.types import MessageCallback, MessageCreated
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.core.schemas import LessonResult, SearchResult
from src.core.services.search import SearchService
from src.core.services.user import UserService
from src.max.formatters import format_text_results
from src.max.keyboards import clarify_keyboard, registration_keyboard, search_pagination_keyboard

router = Router(router_id="max_search")
search_service = SearchService()
user_service = UserService()


@router.message_created(F.message.body.text)
async def handle_search(event: MessageCreated, context: MemoryContext, session: AsyncSession):
    """Catch-all: any text message from registered user triggers search."""
    user = await user_service.get_by_max_user_id(session, event.message.sender.user_id)
    if not user:
        settings = get_settings()
        if settings.web_app_url and settings.max_bot_username:
            kb = registration_keyboard(
                bot_username=settings.max_bot_username,
                bot_contact_id=settings.max_bot_id or None,
            )
            await event.message.answer(
                "Вы ещё не зарегистрированы. Пройдите регистрацию:",
                attachments=[kb.as_markup()],
            )
        else:
            await event.message.answer(
                "Вы ещё не зарегистрированы. Нажмите /start для регистрации."
            )
        return

    query = event.message.body.text.strip()
    if len(query) < 2:
        await event.message.answer("Слишком короткий запрос. Введите минимум 2 символа.")
        return

    await context.update_data(search_query=query, search_filtered=None, clarify_stage=None)

    result = await search_service.hybrid_search(session, query, page=1)

    # Check if clarification might be needed
    if result.total > search_service.clarify_threshold:
        all_lessons = await search_service.fts_search_all(session, query)
        clarification = search_service.check_clarification(all_lessons, stage="subject")
        if clarification:
            await context.update_data(
                search_results=[l.model_dump() for l in all_lessons],
                search_total=result.total,
                clarify_stage="subject",
                clarify_dominant=clarification.dominant_value,
            )
            kb = clarify_keyboard(clarification.dominant_value)
            await event.message.answer(clarification.message, attachments=[kb.as_markup()])
            return

    text = format_text_results(result)
    if result.total_pages > 0:
        kb = search_pagination_keyboard(1, result.total_pages)
        await event.message.answer(text, attachments=[kb.as_markup()])
    else:
        await event.message.answer(text)


@router.message_callback(F.callback.payload.startswith("clarify:"))
async def handle_clarification(event: MessageCallback, context: MemoryContext, session: AsyncSession):
    choice = event.callback.payload.split(":")[1]  # "dominant" or "all"
    data = await context.get_data()

    all_lessons = [LessonResult(**l) for l in data.get("search_results", [])]
    query = data.get("search_query", "")
    stage = data.get("clarify_stage", "subject")
    dominant = data.get("clarify_dominant", "")

    if choice == "dominant":
        field = "subject" if stage == "subject" else "topic"
        filtered = [l for l in all_lessons if getattr(l, field) == dominant]
    else:
        filtered = all_lessons

    # Check for second-level clarification (topic)
    if choice == "dominant" and stage == "subject":
        clarification = search_service.check_clarification(
            filtered, stage="topic", selected_subject=dominant,
        )
        if clarification:
            await context.update_data(
                search_results=[l.model_dump() for l in filtered],
                clarify_stage="topic",
                clarify_dominant=clarification.dominant_value,
                clarify_subject=dominant,
            )
            kb = clarify_keyboard(clarification.dominant_value)
            await event.bot.edit_message(
                message_id=event.message.body.mid,
                text=clarification.message,
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
        clarify_stage=None,
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


@router.message_callback(F.callback.payload.startswith("search:page:"))
async def paginate_search(event: MessageCallback, context: MemoryContext, session: AsyncSession):
    page = int(event.callback.payload.split(":")[-1])
    data = await context.get_data()
    query = data.get("search_query", "")

    # Check if we have filtered results from clarification
    filtered_data = data.get("search_filtered")
    if filtered_data:
        filtered = [LessonResult(**l) for l in filtered_data]
        per_page = search_service.per_page
        offset = (page - 1) * per_page
        page_lessons = filtered[offset : offset + per_page]
        result = SearchResult(
            query=query, lessons=page_lessons,
            total=len(filtered), page=page, per_page=per_page,
        )
    else:
        result = await search_service.hybrid_search(session, query, page=page)

    text = format_text_results(result)
    kb = search_pagination_keyboard(page, result.total_pages)
    await event.bot.edit_message(
        message_id=event.message.body.mid,
        text=text,
        attachments=[kb.as_markup()],
    )
```

**Step 2: Commit**

```bash
git add src/max/handlers/search.py
git commit -m "feat: add clarification flow to Max search handler"
```

---

### Task 8: Manual testing

**Step 1: Start bot locally**

Run the bot and test these scenarios:

1. **Below threshold** — search with few results → no clarification, results shown directly
2. **Above threshold, multiple subjects** — search with many results across subjects → subject clarification shown
3. **Pick dominant subject, above threshold, multiple topics** → topic clarification shown
4. **Pick "Все найденные"** at any stage → all results shown with pagination
5. **Pagination after clarification** → page navigation works on filtered results
6. **New search after clarification** → state is cleared, fresh search works

**Step 2: Final commit**

```bash
git add -A
git commit -m "feat: search clarification for large result sets"
```
