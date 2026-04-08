# Search Levels Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace automatic AND→OR→semantic cascade with explicit 3-level search controlled by "Расширить поиск" button.

**Architecture:** `SearchService` gets `search_by_level` (paginated) and `get_all_lessons_for_level` (all results for clarification); `fts_search_all` gains `use_or` flag; both bot keyboards add `level` param to `search_pagination_keyboard`; both bot handlers add `search:expand` callback and use new service methods.

**Tech Stack:** Python, SQLAlchemy async, aiogram (Telegram), maxapi (MAX), pytest.

---

### Task 1: Update SearchService — add `search_by_level`, `get_all_lessons_for_level`, update `fts_search_all`

**Files:**
- Modify: `src/core/services/search.py`
- Test: `tests/test_search.py`

**Context:**
- `fts_search_all` currently: AND-only, returns all lessons (no pagination)
- `hybrid_search` will be **removed** (replaced by `search_by_level`)
- `_build_tsquery` = AND, `_build_tsquery_or` = OR (from previous feature)
- `LessonResult` has no `id` field — deduplication uses `url`

**Step 1: Write failing tests**

Add to `tests/test_search.py`:

```python
# --- search_by_level tests ---

@pytest.mark.asyncio
@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
async def test_search_by_level_1_returns_and_fts(mock_settings):
    """Level 1 returns AND FTS results directly."""
    service = SearchService()
    lessons = [_make_lesson() for _ in range(3)]
    with patch.object(service, "fts_search", new_callable=AsyncMock) as mock_fts:
        mock_fts.return_value = (lessons, 3)
        result = await service.search_by_level(MagicMock(), "история", level=1)
    assert result.total == 3
    assert mock_fts.call_count == 1


@pytest.mark.asyncio
@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
async def test_search_by_level_2_combines_and_semantic(mock_settings):
    """Level 2 returns AND + semantic, deduplicated by URL."""
    service = SearchService()
    and_lesson = _make_lesson(subject="История")
    sem_lesson = LessonResult(
        title="Семантика", url="https://example.com/sem",
        subject="История", grade=8, section="Раздел", topic="Тема",
    )
    with patch.object(service, "fts_search_all", new_callable=AsyncMock) as mock_all, \
         patch.object(service, "semantic_search", new_callable=AsyncMock) as mock_sem, \
         patch("src.core.services.search.select") as mock_select:
        mock_all.return_value = [and_lesson]
        mock_sem.return_value = [sem_lesson]
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        result = await service.search_by_level(mock_session, "история", level=2)
    assert result.total == 2


@pytest.mark.asyncio
@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
async def test_search_by_level_2_deduplicates_by_url(mock_settings):
    """Level 2 deduplicates lessons with same URL."""
    service = SearchService()
    lesson = _make_lesson(subject="История")
    duplicate = LessonResult(
        title="Дубль", url=lesson.url,  # same URL
        subject="История", grade=8, section="Раздел", topic="Тема",
    )
    with patch.object(service, "fts_search_all", new_callable=AsyncMock) as mock_all, \
         patch.object(service, "semantic_search", new_callable=AsyncMock) as mock_sem, \
         patch("src.core.services.search.select"):
        mock_all.return_value = [lesson]
        mock_sem.return_value = [duplicate]
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        result = await service.search_by_level(mock_session, "история", level=2)
    assert result.total == 1


@pytest.mark.asyncio
@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
async def test_search_by_level_3_adds_or_results(mock_settings):
    """Level 3 adds OR FTS results not already in AND+semantic."""
    service = SearchService()
    and_lesson = _make_lesson(subject="История")
    or_lesson = LessonResult(
        title="OR урок", url="https://example.com/or",
        subject="Математика", grade=5, section="Раздел", topic="Тема",
    )
    with patch.object(service, "fts_search_all", new_callable=AsyncMock) as mock_all, \
         patch.object(service, "semantic_search", new_callable=AsyncMock) as mock_sem, \
         patch("src.core.services.search.select"):
        # First call: AND (use_or=False), second call: OR (use_or=True)
        mock_all.side_effect = [[and_lesson], [or_lesson]]
        mock_sem.return_value = []
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        result = await service.search_by_level(mock_session, "история", level=3)
    assert result.total == 2
    assert mock_all.call_count == 2
    # Verify second call used use_or=True
    assert mock_all.call_args_list[1].kwargs.get("use_or", False) is True
```

**Step 2: Run to confirm FAIL**

```bash
python -m pytest tests/test_search.py::test_search_by_level_1_returns_and_fts tests/test_search.py::test_search_by_level_2_combines_and_semantic -v
```
Expected: FAIL — `search_by_level` not defined.

**Step 3: Add `use_or` to `fts_search_all` and implement new methods**

In `src/core/services/search.py`:

1. Update `fts_search_all` signature (add `use_or: bool = False`):

```python
async def fts_search_all(self, session: AsyncSession, query: str, use_or: bool = False) -> list[LessonResult]:
    """Fetch all FTS results without pagination (for clarification analysis)."""
    ts_query = _build_tsquery_or(query) if use_or else _build_tsquery(query)
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
            grade=l.grade,
            section=l.section,
            topic=l.topic,
            is_semantic=False,
        )
        for l in result.scalars().unique().all()
    ]
```

2. Add `_build_level_results` private helper and `search_by_level` method after `fts_search_all`:

```python
async def _build_level_results(self, session: AsyncSession, query: str, level: int) -> list[LessonResult]:
    """Build accumulated lesson list for level 2 or 3 (no pagination)."""
    and_lessons = await self.fts_search_all(session, query)

    # Get AND IDs to exclude from semantic search
    and_id_query = select(Lesson.id).where(
        Lesson.search_vector.op("@@")(_build_tsquery(query))
    )
    and_id_result = await session.execute(and_id_query)
    and_ids = [row[0] for row in and_id_result.all()]

    semantic_lessons = await self.semantic_search(session, query, exclude_ids=and_ids)
    combined = and_lessons + semantic_lessons

    if level >= 3:
        seen_urls = {l.url for l in combined}
        or_lessons = await self.fts_search_all(session, query, use_or=True)
        combined += [l for l in or_lessons if l.url not in seen_urls]

    return combined

async def search_by_level(self, session: AsyncSession, query: str, level: int, page: int = 1) -> SearchResult:
    """Search at the given level (1=AND, 2=AND+semantic, 3=AND+semantic+OR), paginated."""
    if level == 1:
        lessons, total = await self.fts_search(session, query, page=page)
        return SearchResult(query=query, lessons=lessons, total=total, page=page, per_page=self.per_page)

    combined = await self._build_level_results(session, query, level)
    total = len(combined)
    offset = (page - 1) * self.per_page
    return SearchResult(
        query=query,
        lessons=combined[offset: offset + self.per_page],
        total=total,
        page=page,
        per_page=self.per_page,
    )

async def get_all_lessons_for_level(self, session: AsyncSession, query: str, level: int) -> list[LessonResult]:
    """Get all lessons for a level without pagination — for clarification analysis."""
    if level == 1:
        return await self.fts_search_all(session, query)
    return await self._build_level_results(session, query, level)
```

3. **Remove `hybrid_search`** (delete the entire method, lines ~107-138).

**Step 4: Run all new tests**

```bash
python -m pytest tests/test_search.py::test_search_by_level_1_returns_and_fts tests/test_search.py::test_search_by_level_2_combines_and_semantic tests/test_search.py::test_search_by_level_2_deduplicates_by_url tests/test_search.py::test_search_by_level_3_adds_or_results -v
```
Expected: all PASS.

**Step 5: Run full test suite — expect hybrid_search tests to fail**

```bash
python -m pytest tests/test_search.py -v
```
The 3 hybrid_search tests (`test_hybrid_search_*`) will now FAIL because `hybrid_search` was removed. That is expected — they will be deleted in this step.

Delete the three tests that reference `hybrid_search`:
- `test_hybrid_search_uses_or_fallback_when_and_insufficient`
- `test_hybrid_search_uses_and_when_sufficient`
- `test_hybrid_search_uses_semantic_when_or_also_insufficient`

Run again:
```bash
python -m pytest tests/test_search.py -v
```
Expected: all pass (2 pre-existing failures in test_models.py are unrelated).

**Step 6: Commit**

```bash
git add src/core/services/search.py tests/test_search.py
git commit -m "feat: add search_by_level, get_all_lessons_for_level; remove hybrid_search"
```

---

### Task 2: Update keyboards — add `level` param and "Расширить поиск" button

**Files:**
- Modify: `src/telegram/keyboards.py`
- Modify: `src/max/keyboards.py`

No tests needed for keyboard builders (they are pure UI helpers with no logic).

**Step 1: Update `search_pagination_keyboard` in Telegram**

In `src/telegram/keyboards.py`, replace `search_pagination_keyboard`:

```python
def search_pagination_keyboard(page: int, total_pages: int, level: int = 1) -> InlineKeyboardMarkup:
    buttons = []
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="\u25c0 Назад", callback_data=f"search:page:{page - 1}"))
    nav_row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Далее \u25b6", callback_data=f"search:page:{page + 1}"))
    buttons.append(nav_row)
    if level < 3:
        buttons.append([
            InlineKeyboardButton(text="\U0001f50d Расширить поиск", callback_data="search:expand")
        ])
    buttons.append([
        InlineKeyboardButton(text="\U0001f504 Новый поиск", callback_data="new_search")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
```

**Step 2: Update `search_pagination_keyboard` in MAX**

In `src/max/keyboards.py`, replace `search_pagination_keyboard`:

```python
def search_pagination_keyboard(page: int, total_pages: int, level: int = 1) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    nav_row = []
    if page > 1:
        nav_row.append(CallbackButton(text="\u25c0 Назад", payload=f"search:page:{page - 1}"))
    nav_row.append(CallbackButton(text=f"{page}/{total_pages}", payload="noop"))
    if page < total_pages:
        nav_row.append(CallbackButton(text="Далее \u25b6", payload=f"search:page:{page + 1}"))
    kb.row(*nav_row)
    if level < 3:
        kb.row(CallbackButton(text="\U0001f50d Расширить поиск", payload="search:expand"))
    kb.row(CallbackButton(text="\U0001f504 Новый поиск", payload="new_search"))
    return kb
```

**Step 3: Commit**

```bash
git add src/telegram/keyboards.py src/max/keyboards.py
git commit -m "feat: add level param and 'Расширить поиск' button to search_pagination_keyboard"
```

---

### Task 3: Update Telegram search handler

**Files:**
- Modify: `src/telegram/handlers/search.py`

**Context — current handler flow:**
- `handle_search`: calls `hybrid_search`, then `fts_search_all` for clarification
- `handle_clarification`: uses `search_results` state key
- `paginate_search`: calls `hybrid_search` for re-query

**New flow:**
- `handle_search`: calls `get_all_lessons_for_level(level=1)`, stores in `search_all_lessons`, always stores `search_level=1`
- `handle_expand` (NEW): reads level from state, increments, fetches all lessons for new level
- `handle_clarification`: reads from `search_all_lessons` (rename from `search_results`)
- `paginate_search`: paginates from `search_all_lessons` in-memory; if no stored lessons (shouldn't happen), re-queries level 1

**Step 1: Rewrite `src/telegram/handlers/search.py`**

```python
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from src.config import get_settings
from src.core.schemas import LessonResult, SearchResult
from src.core.services.search import SearchService
from src.core.services.user import UserService
from src.telegram.formatters import format_text_results
from src.telegram.keyboards import clarify_keyboard, search_pagination_keyboard

router = Router()
search_service = SearchService()
user_service = UserService()


@router.message(F.text)
async def handle_search(message: Message, state: FSMContext, session):
    """Catch-all: any text message from registered user triggers search."""
    user = await user_service.get_by_telegram_id(session, message.from_user.id)
    if not user:
        settings = get_settings()
        if settings.web_app_url:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="Зарегистрироваться",
                    web_app=WebAppInfo(url=settings.web_app_url),
                )]
            ])
            await message.answer(
                "Вы ещё не зарегистрированы. Пройдите регистрацию:",
                reply_markup=keyboard,
            )
        else:
            await message.answer(
                "Вы ещё не зарегистрированы. Нажмите /start для регистрации."
            )
        return

    if not user.consent_given:
        await message.answer(
            "Для использования поиска необходимо дать согласие на обработку персональных данных.\n\n"
            "Нажмите /start, чтобы получить запрос на согласие повторно."
        )
        return

    query = message.text.strip()
    if len(query) < 2:
        await message.answer("Слишком короткий запрос. Введите минимум 2 символа.")
        return

    await _run_search(message=message, state=state, session=session, query=query, level=1, edit=False)


@router.callback_query(F.data == "search:expand")
async def handle_expand(callback: CallbackQuery, state: FSMContext, session):
    """Expand search to the next level."""
    data = await state.get_data()
    query = data.get("search_query", "")
    current_level = data.get("search_level", 1)
    new_level = min(current_level + 1, 3)
    await _run_search(callback=callback, state=state, session=session, query=query, level=new_level, edit=True)
    await callback.answer()


async def _run_search(*, state: FSMContext, session, query: str, level: int, edit: bool,
                      message=None, callback=None):
    """Shared logic: fetch all lessons for level, check clarification, show results."""
    all_lessons = await search_service.get_all_lessons_for_level(session, query, level)

    await state.update_data(
        search_query=query,
        search_level=level,
        search_all_lessons=[l.model_dump() for l in all_lessons],
        search_filtered=None,
        clarify_result=None,
    )

    clarification = search_service.check_clarification(all_lessons)
    if clarification:
        await state.update_data(clarify_result=clarification.model_dump())
        options = [o.model_dump() for o in clarification.options]
        keyboard = clarify_keyboard(options, clarification.level)
        if edit and callback:
            await callback.message.edit_text(clarification.message, reply_markup=keyboard)
        else:
            await message.answer(clarification.message, reply_markup=keyboard)
        return

    per_page = search_service.per_page
    page_lessons = all_lessons[:per_page]
    total = len(all_lessons)
    result = SearchResult(query=query, lessons=page_lessons, total=total, page=1, per_page=per_page)
    text = format_text_results(result)
    keyboard = search_pagination_keyboard(1, result.total_pages, level) if result.total_pages > 0 else None

    if edit and callback:
        await callback.message.edit_text(text, reply_markup=keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("clarify:"))
async def handle_clarification(callback: CallbackQuery, state: FSMContext, session):
    parts = callback.data.split(":")  # clarify:{level}:{index_or_all}
    level = parts[1]
    choice = parts[2]

    data = await state.get_data()
    all_lessons = [LessonResult(**l) for l in data.get("search_all_lessons", [])]
    query = data.get("search_query", "")
    search_level = data.get("search_level", 1)
    clarify_data = data.get("clarify_result", {})

    if choice == "all":
        filtered = all_lessons
    else:
        idx = int(choice)
        options = clarify_data.get("options", [])
        selected_value = options[idx]["value"]
        field = level
        filtered = [
            l for l in all_lessons
            if str(getattr(l, field) or "") == selected_value
        ]

    next_clarification = search_service.check_clarification(filtered)
    if next_clarification:
        await state.update_data(
            search_all_lessons=[l.model_dump() for l in filtered],
            clarify_result=next_clarification.model_dump(),
        )
        options = [o.model_dump() for o in next_clarification.options]
        keyboard = clarify_keyboard(options, next_clarification.level)
        await callback.message.edit_text(next_clarification.message, reply_markup=keyboard)
        await callback.answer()
        return

    total = len(filtered)
    per_page = search_service.per_page
    page_lessons = filtered[:per_page]
    search_result = SearchResult(query=query, lessons=page_lessons, total=total, page=1, per_page=per_page)
    text = format_text_results(search_result)

    await state.update_data(
        search_filtered=[l.model_dump() for l in filtered],
        clarify_result=None,
    )

    keyboard = search_pagination_keyboard(1, search_result.total_pages, search_level) if search_result.total_pages > 0 else None
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("search:page:"))
async def paginate_search(callback: CallbackQuery, state: FSMContext, session):
    page = int(callback.data.split(":")[-1])
    data = await state.get_data()
    query = data.get("search_query", "")
    search_level = data.get("search_level", 1)

    filtered_data = data.get("search_filtered")
    all_data = data.get("search_all_lessons")

    if filtered_data:
        lessons = [LessonResult(**l) for l in filtered_data]
    elif all_data:
        lessons = [LessonResult(**l) for l in all_data]
    else:
        # Fallback: re-query level 1 from DB
        result = await search_service.search_by_level(session, query, level=1, page=page)
        text = format_text_results(result)
        keyboard = search_pagination_keyboard(page, result.total_pages, search_level)
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()
        return

    per_page = search_service.per_page
    offset = (page - 1) * per_page
    page_lessons = lessons[offset: offset + per_page]
    result = SearchResult(query=query, lessons=page_lessons, total=len(lessons), page=page, per_page=per_page)
    text = format_text_results(result)
    keyboard = search_pagination_keyboard(page, result.total_pages, search_level)
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()
```

**Step 2: Run search tests**

```bash
python -m pytest tests/ -v -k "search" 2>&1 | tail -20
```
Expected: all search tests pass.

**Step 3: Commit**

```bash
git add src/telegram/handlers/search.py
git commit -m "feat: update Telegram search handler — search_by_level, expand handler, in-memory pagination"
```

---

### Task 4: Update MAX search handler

**Files:**
- Modify: `src/max/handlers/search.py`

Mirrors Task 3 exactly but uses MAX API patterns (`MemoryContext`, `MessageCreated`, `MessageCallback`, `event.bot.edit_message`).

**Step 1: Rewrite `src/max/handlers/search.py`**

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

    if not user.consent_given:
        await event.message.answer(
            "Для использования поиска необходимо дать согласие на обработку персональных данных.\n\n"
            "Нажмите /start, чтобы получить запрос на согласие повторно."
        )
        return

    query = event.message.body.text.strip()
    if len(query) < 2:
        await event.message.answer("Слишком короткий запрос. Введите минимум 2 символа.")
        return

    await _run_search(event=event, context=context, session=session, query=query, level=1, edit=False)


@router.message_callback(F.callback.payload == "search:expand")
async def handle_expand(event: MessageCallback, context: MemoryContext, session: AsyncSession):
    """Expand search to the next level."""
    data = await context.get_data()
    query = data.get("search_query", "")
    current_level = data.get("search_level", 1)
    new_level = min(current_level + 1, 3)
    await _run_search(event=event, context=context, session=session, query=query, level=new_level, edit=True)


async def _run_search(*, event, context: MemoryContext, session, query: str, level: int, edit: bool):
    """Shared logic: fetch all lessons for level, check clarification, show results."""
    all_lessons = await search_service.get_all_lessons_for_level(session, query, level)

    await context.update_data(
        search_query=query,
        search_level=level,
        search_all_lessons=[l.model_dump() for l in all_lessons],
        search_filtered=None,
        clarify_result=None,
    )

    clarification = search_service.check_clarification(all_lessons)
    if clarification:
        await context.update_data(clarify_result=clarification.model_dump())
        options = [o.model_dump() for o in clarification.options]
        kb = clarify_keyboard(options, clarification.level)
        if edit:
            await event.bot.edit_message(
                message_id=event.message.body.mid,
                text=clarification.message,
                attachments=[kb.as_markup()],
            )
        else:
            await event.message.answer(clarification.message, attachments=[kb.as_markup()])
        return

    per_page = search_service.per_page
    page_lessons = all_lessons[:per_page]
    total = len(all_lessons)
    result = SearchResult(query=query, lessons=page_lessons, total=total, page=1, per_page=per_page)
    text = format_text_results(result)

    if result.total_pages > 0:
        kb = search_pagination_keyboard(1, result.total_pages, level)
        if edit:
            await event.bot.edit_message(
                message_id=event.message.body.mid,
                text=text,
                attachments=[kb.as_markup()],
            )
        else:
            await event.message.answer(text, attachments=[kb.as_markup()])
    else:
        if edit:
            await event.bot.edit_message(message_id=event.message.body.mid, text=text)
        else:
            await event.message.answer(text)


@router.message_callback(F.callback.payload.startswith("clarify:"))
async def handle_clarification(event: MessageCallback, context: MemoryContext, session: AsyncSession):
    parts = event.callback.payload.split(":")
    level = parts[1]
    choice = parts[2]

    data = await context.get_data()
    all_lessons = [LessonResult(**l) for l in data.get("search_all_lessons", [])]
    query = data.get("search_query", "")
    search_level = data.get("search_level", 1)
    clarify_data = data.get("clarify_result", {})

    if choice == "all":
        filtered = all_lessons
    else:
        idx = int(choice)
        options = clarify_data.get("options", [])
        selected_value = options[idx]["value"]
        field = level
        filtered = [
            l for l in all_lessons
            if str(getattr(l, field) or "") == selected_value
        ]

    next_clarification = search_service.check_clarification(filtered)
    if next_clarification:
        await context.update_data(
            search_all_lessons=[l.model_dump() for l in filtered],
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

    total = len(filtered)
    per_page = search_service.per_page
    page_lessons = filtered[:per_page]
    search_result = SearchResult(query=query, lessons=page_lessons, total=total, page=1, per_page=per_page)
    text = format_text_results(search_result)

    await context.update_data(
        search_filtered=[l.model_dump() for l in filtered],
        clarify_result=None,
    )

    if search_result.total_pages > 0:
        kb = search_pagination_keyboard(1, search_result.total_pages, search_level)
        await event.bot.edit_message(
            message_id=event.message.body.mid,
            text=text,
            attachments=[kb.as_markup()],
        )
    else:
        await event.bot.edit_message(message_id=event.message.body.mid, text=text)


@router.message_callback(F.callback.payload.startswith("search:page:"))
async def paginate_search(event: MessageCallback, context: MemoryContext, session: AsyncSession):
    page = int(event.callback.payload.split(":")[-1])
    data = await context.get_data()
    query = data.get("search_query", "")
    search_level = data.get("search_level", 1)

    filtered_data = data.get("search_filtered")
    all_data = data.get("search_all_lessons")

    if filtered_data:
        lessons = [LessonResult(**l) for l in filtered_data]
    elif all_data:
        lessons = [LessonResult(**l) for l in all_data]
    else:
        result = await search_service.search_by_level(session, query, level=1, page=page)
        text = format_text_results(result)
        kb = search_pagination_keyboard(page, result.total_pages, search_level)
        await event.bot.edit_message(
            message_id=event.message.body.mid,
            text=text,
            attachments=[kb.as_markup()],
        )
        return

    per_page = search_service.per_page
    offset = (page - 1) * per_page
    page_lessons = lessons[offset: offset + per_page]
    result = SearchResult(query=query, lessons=page_lessons, total=len(lessons), page=page, per_page=per_page)
    text = format_text_results(result)
    kb = search_pagination_keyboard(page, result.total_pages, search_level)
    await event.bot.edit_message(
        message_id=event.message.body.mid,
        text=text,
        attachments=[kb.as_markup()],
    )
```

**Step 2: Run full test suite**

```bash
python -m pytest tests/ -v 2>&1 | tail -20
```
Expected: all pass (pre-existing test_models.py failures are unrelated).

**Step 3: Commit**

```bash
git add src/max/handlers/search.py
git commit -m "feat: update MAX search handler — search_by_level, expand handler, in-memory pagination"
```
