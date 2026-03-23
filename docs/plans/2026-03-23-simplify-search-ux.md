# Simplify Search UX Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Any text message from a registered user triggers hybrid search directly — no menu, no buttons. Parameter search available as "Уточнить" button on results.

**Architecture:** Remove the two-button main menu. Add a catch-all message handler that checks registration and runs `hybrid_search()`. Keep param_search as a refinement flow accessible from search results via an inline button.

**Tech Stack:** aiogram 3, SQLAlchemy async, PostgreSQL FTS + pgvector

---

## Current State

- `main_menu_keyboard()` shows two buttons: "Поиск по параметрам" and "Поиск по словам"
- `text_search.py` uses FSM state `TextSearchStates.waiting_query` to capture query
- `param_search.py` is a standalone flow triggered from menu
- After onboarding and on `/start` return, user sees the menu

## Target State

- No main menu after onboarding — just a text prompt: "Просто напишите, что вы ищете"
- Any text message → `hybrid_search()` (if user registered)
- If not registered → start onboarding
- Search results show "Уточнить по параметрам" button → param_search flow
- "Новый поиск" button in pagination replaced with text hint
- `TextSearchStates` FSM removed (no longer needed)

---

### Task 1: Remove main menu keyboard and TextSearchStates

**Files:**
- Modify: `src/telegram/keyboards.py:9-13` (remove `main_menu_keyboard`)
- Modify: `src/telegram/handlers/text_search.py` (remove entirely — will be replaced by new handler)
- Modify: `src/telegram/handlers/__init__.py` (remove `text_search_router` import)

**Step 1: Delete `main_menu_keyboard` from keyboards.py**

Remove the function (lines 9-13):
```python
def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f50d Поиск по параметрам", callback_data="search_params")],
        [InlineKeyboardButton(text="\U0001f4ac Поиск по словам", callback_data="search_text")],
    ])
```

**Step 2: Delete `src/telegram/handlers/text_search.py`**

This entire file is replaced by the new search handler in Task 3.

**Step 3: Remove text_search_router from `__init__.py`**

Remove the import and the `parent_router.include_router(text_search_router)` line.

**Step 4: Commit**

```bash
git add -u
git commit -m "refactor: remove main menu keyboard and text search handler"
```

---

### Task 2: Update start.py — no menu after onboarding

**Files:**
- Modify: `src/telegram/handlers/start.py:32-46` (cmd_start)
- Modify: `src/telegram/handlers/start.py:180-197` (_finish_onboarding)

**Step 1: Update `cmd_start` for returning users**

Replace the menu display with a simple text message:
```python
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, session):
    user = await user_service.get_by_telegram_id(session, message.from_user.id)
    if user:
        await state.clear()
        await message.answer(
            f"С возвращением, {user.full_name}!\n\n"
            "Просто напишите, что вы ищете, и я найду подходящие уроки."
        )
        return
    await state.set_state(OnboardingStates.full_name)
    await message.answer(
        "Добро пожаловать! Давайте зарегистрируемся.\n\n"
        "Введите ваше имя и фамилию:"
    )
```

**Step 2: Update `_finish_onboarding`**

Replace:
```python
await message.answer(
    "Регистрация завершена! Выберите действие:",
    reply_markup=main_menu_keyboard(),
)
```

With:
```python
await message.answer(
    "Регистрация завершена!\n\n"
    "Просто напишите, что вы ищете, и я найду подходящие уроки."
)
```

**Step 3: Remove `main_menu_keyboard` import from start.py**

Remove `main_menu_keyboard` from the import line (keep the others).

**Step 4: Commit**

```bash
git add src/telegram/handlers/start.py
git commit -m "refactor: replace menu with text prompt after onboarding"
```

---

### Task 3: Create catch-all search handler

**Files:**
- Create: `src/telegram/handlers/search.py`
- Modify: `src/telegram/handlers/__init__.py` (add search_router, must be LAST)

**Step 1: Create `src/telegram/handlers/search.py`**

```python
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.core.services.search import SearchService
from src.core.services.user import UserService
from src.telegram.formatters import format_text_results
from src.telegram.keyboards import search_pagination_keyboard

router = Router()
search_service = SearchService()
user_service = UserService()


@router.message(F.text)
async def handle_search(message: Message, state: FSMContext, session):
    """Catch-all: any text message from registered user triggers search."""
    user = await user_service.get_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer(
            "Вы ещё не зарегистрированы. Нажмите /start для регистрации."
        )
        return

    query = message.text.strip()
    if len(query) < 2:
        await message.answer("Слишком короткий запрос. Введите минимум 2 символа.")
        return

    await state.update_data(search_query=query)

    result = await search_service.hybrid_search(session, query, page=1)
    text = format_text_results(result)

    keyboard = None
    if result.total_pages > 0:
        keyboard = search_pagination_keyboard(1, result.total_pages)

    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("search:page:"))
async def paginate_search(callback: CallbackQuery, state: FSMContext, session):
    page = int(callback.data.split(":")[-1])
    data = await state.get_data()
    query = data.get("search_query", "")

    result = await search_service.hybrid_search(session, query, page=page)
    text = format_text_results(result)
    keyboard = search_pagination_keyboard(page, result.total_pages)

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()
```

**Step 2: Register search_router LAST in `__init__.py`**

The search router must be last because it's a catch-all for any text message. Onboarding FSM handlers (in start_router) must match first.

```python
from aiogram import Router

from src.telegram.handlers.admin import router as admin_router
from src.telegram.handlers.menu import router as menu_router
from src.telegram.handlers.param_search import router as param_search_router
from src.telegram.handlers.search import router as search_router
from src.telegram.handlers.start import router as start_router


def register_all_routers(parent_router: Router) -> None:
    parent_router.include_router(start_router)
    parent_router.include_router(admin_router)
    parent_router.include_router(menu_router)
    parent_router.include_router(param_search_router)
    parent_router.include_router(search_router)  # catch-all — must be last
```

**Step 3: Commit**

```bash
git add src/telegram/handlers/search.py src/telegram/handlers/__init__.py
git commit -m "feat: add catch-all search handler for any text message"
```

---

### Task 4: Update keyboards — new search_pagination_keyboard with "Уточнить" button

**Files:**
- Modify: `src/telegram/keyboards.py`

**Step 1: Add `search_pagination_keyboard` function**

Add after existing `pagination_keyboard`:

```python
def search_pagination_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    buttons = []
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="\u25c0 Назад", callback_data=f"search:page:{page - 1}"))
    nav_row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Далее \u25b6", callback_data=f"search:page:{page + 1}"))
    buttons.append(nav_row)
    buttons.append([
        InlineKeyboardButton(text="\U0001f50d Уточнить по параметрам", callback_data="search_params")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
```

This replaces the old "Новый поиск" button with "Уточнить по параметрам" which enters the param_search flow.

**Step 2: Commit**

```bash
git add src/telegram/keyboards.py
git commit -m "feat: add search pagination keyboard with refine button"
```

---

### Task 5: Update menu.py — remove "new_search" handler or redirect

**Files:**
- Modify: `src/telegram/handlers/menu.py`

**Step 1: Update `new_search` callback**

The "Новый поиск" callback is still used by param_search pagination. Update it to just prompt for new text:

```python
@router.callback_query(F.data == "new_search")
async def new_search(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Просто напишите, что вы ищете."
    )
    await callback.answer()
```

**Step 2: Commit**

```bash
git add src/telegram/handlers/menu.py
git commit -m "refactor: update new_search to prompt for text input"
```

---

### Task 6: Update formatters — remove reference to "поиск по параметрам"

**Files:**
- Modify: `src/telegram/formatters.py:30-33`

**Step 1: Update empty results message**

Replace:
```python
return (
    f'\U0001f50e По запросу \u00ab{result.query}\u00bb ничего не найдено.\n'
    "Попробуйте другие ключевые слова или поиск по параметрам."
)
```

With:
```python
return (
    f'\U0001f50e По запросу \u00ab{result.query}\u00bb ничего не найдено.\n'
    "Попробуйте другие ключевые слова."
)
```

**Step 2: Commit**

```bash
git add src/telegram/formatters.py
git commit -m "refactor: update empty results message"
```

---

### Task 7: Verify and test

**Step 1: Run existing tests**

```bash
python -m pytest tests/ -v
```

Expected: all pass (or known failures unrelated to our changes).

**Step 2: Manual verification checklist**

- [ ] `/start` for new user → starts onboarding, no menu
- [ ] `/start` for returning user → text prompt, no buttons
- [ ] Text message from registered user → hybrid search results
- [ ] Text message from unregistered user → "/start для регистрации"
- [ ] Pagination works on search results
- [ ] "Уточнить по параметрам" button → enters param search flow
- [ ] Param search flow still works end-to-end
- [ ] Onboarding text input (name, phone, email) is NOT caught by search handler

**Step 3: Final commit if any fixes needed**
