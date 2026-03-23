# MAX Messenger Bot Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add MAX messenger bot as a third interface to the AITSOK search platform, mirroring Telegram bot functionality.

**Architecture:** Parallel `src/max/` directory mirroring `src/telegram/`, sharing `src/core/` services. Both bots run in one process via `asyncio.gather` with enable/disable flags.

**Tech Stack:** maxapi (async Python SDK for MAX messenger, aiogram-inspired), SQLAlchemy, FastAPI, Alembic

---

### Task 1: Dependencies and Config

**Files:**
- Modify: `requirements.txt`
- Modify: `src/config.py`
- Modify: `.env`

**Step 1: Add maxapi to requirements**

In `requirements.txt`, add:
```
maxapi>=0.9.17
```

**Step 2: Add config fields**

In `src/config.py`, add three fields to `Settings`:

```python
class Settings(BaseSettings):
    bot_token: str
    max_bot_token: str = ""
    enable_telegram: bool = True
    enable_max: bool = True
    admin_ids_str: str = Field(default="", alias="ADMIN_IDS")
    # ... rest unchanged
```

**Step 3: Add env vars to `.env`**

```
MAX_BOT_TOKEN=
ENABLE_TELEGRAM=true
ENABLE_MAX=true
```

**Step 4: Install dependency**

Run: `pip install maxapi>=0.9.17`

**Step 5: Commit**

```bash
git add requirements.txt src/config.py .env
git commit -m "feat: add maxapi dependency and config for MAX bot"
```

---

### Task 2: Database — add max_user_id column

**Files:**
- Modify: `src/core/models.py:53-68`
- Modify: `src/core/schemas.py:6-13`
- Modify: `src/core/services/user.py`
- Create: Alembic migration

**Step 1: Add max_user_id to User model**

In `src/core/models.py`, add after `telegram_id`:

```python
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    max_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    # ... rest unchanged
```

**Step 2: Add max_user_id to UserCreate schema**

In `src/core/schemas.py`:

```python
class UserCreate(BaseModel):
    telegram_id: int | None = None
    max_user_id: int | None = None
    full_name: str
    # ... rest unchanged
```

**Step 3: Add get_by_max_user_id and update create_user in UserService**

In `src/core/services/user.py`, add method:

```python
async def get_by_max_user_id(self, session: AsyncSession, max_user_id: int) -> User | None:
    result = await session.execute(select(User).where(User.max_user_id == max_user_id))
    return result.scalar_one_or_none()
```

Update `create_user` to include `max_user_id`:

```python
async def create_user(self, session: AsyncSession, data: UserCreate) -> User:
    user = User(
        telegram_id=data.telegram_id,
        max_user_id=data.max_user_id,
        full_name=data.full_name,
        phone=data.phone,
        email=data.email,
        region_id=data.region_id,
        school_id=data.school_id,
        subjects=data.subjects,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
```

**Step 4: Generate Alembic migration**

Run: `alembic revision --autogenerate -m "add max_user_id to users"`

Verify the generated migration adds `max_user_id` column.

**Step 5: Apply migration**

Run: `alembic upgrade head`

**Step 6: Commit**

```bash
git add src/core/models.py src/core/schemas.py src/core/services/user.py alembic/versions/
git commit -m "feat: add max_user_id column to users table"
```

---

### Task 3: MAX bot core — Bot, Dispatcher, Middleware

**Files:**
- Create: `src/max/__init__.py`
- Create: `src/max/bot.py`
- Create: `src/max/middlewares.py`

**Step 1: Create package init**

`src/max/__init__.py` — empty file.

**Step 2: Create bot.py**

```python
from maxapi import Bot, Dispatcher

from src.config import get_settings


def create_max_bot() -> Bot:
    return Bot(token=get_settings().max_bot_token)


def create_max_dispatcher() -> Dispatcher:
    return Dispatcher()
```

**Step 3: Create middlewares.py**

```python
from typing import Any, Awaitable, Callable

from maxapi.filters.middleware import BaseMiddleware
from maxapi.types import UpdateUnion

from src.core.database import get_async_session


class DatabaseMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event_object: UpdateUnion,
        data: dict[str, Any],
    ) -> Any:
        session_factory = get_async_session()
        async with session_factory() as session:
            data["session"] = session
            return await handler(event_object, data)
```

**Step 4: Commit**

```bash
git add src/max/
git commit -m "feat: add MAX bot core — Bot, Dispatcher, DatabaseMiddleware"
```

---

### Task 4: MAX keyboards

**Files:**
- Create: `src/max/keyboards.py`

**Step 1: Create keyboards.py**

Port all keyboard functions from `src/telegram/keyboards.py`, replacing aiogram types with maxapi types.

```python
from maxapi.types import CallbackButton, RequestContactButton
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder


def items_keyboard(items: list[dict], callback_prefix: str, add_skip: bool = False) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for item in items:
        btn_id = item.get("id", item.get("name", ""))
        kb.row(CallbackButton(text=item["name"], payload=f"{callback_prefix}:{btn_id}"))
    if add_skip:
        kb.row(CallbackButton(text="\u23ed Пропустить", payload=f"{callback_prefix}:skip"))
    return kb


def grades_keyboard(grades: list[int], callback_prefix: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for g in grades:
        kb.add(CallbackButton(text=str(g), payload=f"{callback_prefix}:{g}"))
    kb.adjust(4)
    return kb


def subjects_toggle_keyboard(subjects: list[dict], selected: set[int]) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for s in subjects:
        mark = "\u2705" if s["id"] in selected else "\u2b1c"
        kb.row(CallbackButton(text=f"{mark} {s['name']}", payload=f"onb_subj:{s['id']}"))
    kb.row(CallbackButton(text="\u2714\ufe0f Готово", payload="onb_subj:done"))
    return kb


def pagination_keyboard(page: int, total_pages: int, callback_prefix: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    row = []
    if page > 1:
        row.append(CallbackButton(text="\u25c0 Назад", payload=f"{callback_prefix}:page:{page - 1}"))
    row.append(CallbackButton(text=f"{page}/{total_pages}", payload="noop"))
    if page < total_pages:
        row.append(CallbackButton(text="Далее \u25b6", payload=f"{callback_prefix}:page:{page + 1}"))
    kb.row(*row)
    kb.row(CallbackButton(text="\U0001f504 Новый поиск", payload="new_search"))
    return kb


def paginated_items_keyboard(
    items: list[dict], callback_prefix: str, page: int = 1, per_page: int = 8,
) -> InlineKeyboardBuilder:
    total_pages = max(1, -(-len(items) // per_page))
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    page_items = items[start : start + per_page]

    kb = InlineKeyboardBuilder()
    for item in page_items:
        btn_id = item.get("id", item.get("name", ""))
        kb.row(CallbackButton(text=item["name"], payload=f"{callback_prefix}:{btn_id}"))

    if total_pages > 1:
        nav_row = []
        if page > 1:
            nav_row.append(CallbackButton(text="\u25c0 Назад", payload=f"{callback_prefix}_page:{page - 1}"))
        nav_row.append(CallbackButton(text=f"{page}/{total_pages}", payload="noop"))
        if page < total_pages:
            nav_row.append(CallbackButton(text="Далее \u25b6", payload=f"{callback_prefix}_page:{page + 1}"))
        kb.row(*nav_row)

    return kb


def search_pagination_keyboard(page: int, total_pages: int) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    nav_row = []
    if page > 1:
        nav_row.append(CallbackButton(text="\u25c0 Назад", payload=f"search:page:{page - 1}"))
    nav_row.append(CallbackButton(text=f"{page}/{total_pages}", payload="noop"))
    if page < total_pages:
        nav_row.append(CallbackButton(text="Далее \u25b6", payload=f"search:page:{page + 1}"))
    kb.row(*nav_row)
    kb.row(CallbackButton(text="\U0001f50d Уточнить по параметрам", payload="search_params"))
    return kb


def contact_keyboard() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(RequestContactButton(text="\U0001f4f1 Отправить контакт"))
    return kb


def skip_keyboard() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="\u23ed Пропустить", payload="onb_skip"))
    return kb
```

**Key differences from Telegram version:**
- Returns `InlineKeyboardBuilder` instead of `InlineKeyboardMarkup`
- Uses `CallbackButton(payload=...)` instead of `InlineKeyboardButton(callback_data=...)`
- Uses `RequestContactButton` instead of `KeyboardButton(request_contact=True)`
- Uses `kb.adjust(4)` for grid layout instead of manual row building
- Keyboards are passed as `attachments=[kb.as_markup()]` when sending messages

**Step 2: Commit**

```bash
git add src/max/keyboards.py
git commit -m "feat: add MAX bot keyboard builders"
```

---

### Task 5: MAX formatters

**Files:**
- Create: `src/max/formatters.py`

**Step 1: Create formatters.py**

The formatters are identical to Telegram — MAX supports the same text formatting. Copy from `src/telegram/formatters.py`:

```python
from src.core.schemas import LessonResult, SearchResult


def format_lesson_param(lesson: LessonResult) -> str:
    return (
        f"\U0001f4da {lesson.title}\n"
        f"\u2192 {lesson.url}"
    )


def format_lesson_text(lesson: LessonResult, index: int) -> str:
    semantic_mark = "\U0001f916 " if lesson.is_semantic else ""
    parts = [p for p in [lesson.subject, lesson.section, lesson.topic] if p]
    context = " | ".join(parts)
    return (
        f"{index}. {semantic_mark}{context}\n"
        f"   \U0001f4da {lesson.title}\n"
        f"   \u2192 {lesson.url}"
    )


def format_param_results(lessons: list[LessonResult]) -> str:
    if not lessons:
        return "Ничего не найдено. Попробуйте изменить параметры поиска."
    return "\n\n".join(format_lesson_param(l) for l in lessons)


def format_text_results(result: SearchResult) -> str:
    if not result.lessons:
        return (
            f'\U0001f50e По запросу \u00ab{result.query}\u00bb ничего не найдено.\n'
            "Попробуйте другие ключевые слова."
        )
    header = f'\U0001f50e По запросу \u00ab{result.query}\u00bb найдено {result.total} результатов:\n\n'
    start_index = (result.page - 1) * result.per_page + 1
    items = "\n\n".join(
        format_lesson_text(l, start_index + i)
        for i, l in enumerate(result.lessons)
    )
    return header + items
```

**Step 2: Commit**

```bash
git add src/max/formatters.py
git commit -m "feat: add MAX bot message formatters"
```

---

### Task 6: MAX handlers — start & onboarding

**Files:**
- Create: `src/max/handlers/__init__.py`
- Create: `src/max/handlers/start.py`

**Step 1: Create handlers/__init__.py**

```python
from maxapi import Dispatcher

from src.max.handlers.admin import router as admin_router
from src.max.handlers.menu import router as menu_router
from src.max.handlers.param_search import router as param_search_router
from src.max.handlers.search import router as search_router
from src.max.handlers.start import router as start_router


def register_all_routers(dp: Dispatcher) -> None:
    dp.include_routers(start_router)
    dp.include_routers(admin_router)
    dp.include_routers(menu_router)
    dp.include_routers(param_search_router)
    dp.include_routers(search_router)  # catch-all — must be last
```

**Step 2: Create start.py**

Key differences from Telegram version:
- `BotStarted` event instead of `CommandStart` filter
- `MemoryContext` instead of `FSMContext`
- `event.message.answer(text, attachments=[kb.as_markup()])` instead of `message.answer(text, reply_markup=kb)`
- `event.callback.payload` instead of `callback.data`
- `event.callback.user.user_id` instead of `callback.from_user.id`
- `bot.edit_message(message_id=..., text=..., attachments=...)` for editing messages with new keyboards
- `Contact()` filter for contact sharing

```python
import logging

from maxapi import F, Router
from maxapi.context import MemoryContext, State, StatesGroup
from maxapi.filters import Contact
from maxapi.types import BotStarted, MessageCallback, MessageCreated

from src.core.schemas import UserCreate
from src.core.services.user import UserService
from src.max.keyboards import (
    contact_keyboard,
    paginated_items_keyboard,
    skip_keyboard,
    subjects_toggle_keyboard,
)

router = Router(router_id="max_start")
user_service = UserService()
logger = logging.getLogger("max.start")


class OnboardingStates(StatesGroup):
    full_name = State()
    region = State()
    school = State()
    subjects = State()
    phone = State()
    email = State()


@router.bot_started()
async def on_bot_started(event: BotStarted, session):
    user = await user_service.get_by_max_user_id(session, event.user.user_id)
    if user:
        await event.bot.send_message(
            chat_id=event.chat_id,
            text=f"С возвращением, {user.full_name}!\n\n"
                 "Просто напишите, что вы ищете, и я найду подходящие уроки.",
        )
        return
    # Note: BotStarted doesn't have context injection by default,
    # so we start onboarding via a welcome message asking for name
    await event.bot.send_message(
        chat_id=event.chat_id,
        text="Добро пожаловать! Давайте зарегистрируемся.\n\n"
             "Введите ваше имя и фамилию:",
    )


@router.message_created(F.message.body.text, OnboardingStates.full_name)
async def process_name(event: MessageCreated, context: MemoryContext, session):
    name = event.message.body.text.strip()
    if len(name.split()) < 2:
        await event.message.answer("Пожалуйста, введите имя и фамилию (минимум 2 слова):")
        return
    await context.update_data(full_name=name)
    await context.set_state(OnboardingStates.region)
    regions = await user_service.get_all_regions(session)
    await context.update_data(all_regions=regions)
    kb = paginated_items_keyboard(regions, "onb_region")
    await event.message.answer("Выберите ваш регион:", attachments=[kb.as_markup()])


@router.message_callback(F.callback.payload.startswith("onb_region_page:"), OnboardingStates.region)
async def process_region_page(event: MessageCallback, context: MemoryContext):
    page = int(event.callback.payload.split(":")[1])
    data = await context.get_data()
    regions = data["all_regions"]
    kb = paginated_items_keyboard(regions, "onb_region", page=page)
    await event.bot.edit_message(
        message_id=event.message.body.mid,
        text="Выберите ваш регион:",
        attachments=[kb.as_markup()],
    )


@router.message_callback(F.callback.payload.startswith("onb_region:"), OnboardingStates.region)
async def process_region_select(event: MessageCallback, context: MemoryContext, session):
    region_id = int(event.callback.payload.split(":")[1])
    await context.update_data(region_id=region_id)
    await context.set_state(OnboardingStates.school)
    schools = await user_service.get_schools_by_region(session, region_id)
    await context.update_data(all_schools=schools)
    kb = paginated_items_keyboard(schools, "onb_school")
    await event.bot.edit_message(
        message_id=event.message.body.mid,
        text="Выберите вашу школу:",
        attachments=[kb.as_markup()],
    )


@router.message_callback(F.callback.payload.startswith("onb_school_page:"), OnboardingStates.school)
async def process_school_page(event: MessageCallback, context: MemoryContext):
    page = int(event.callback.payload.split(":")[1])
    data = await context.get_data()
    schools = data["all_schools"]
    kb = paginated_items_keyboard(schools, "onb_school", page=page)
    await event.bot.edit_message(
        message_id=event.message.body.mid,
        text="Выберите вашу школу:",
        attachments=[kb.as_markup()],
    )


@router.message_callback(F.callback.payload.startswith("onb_school:"), OnboardingStates.school)
async def process_school_select(event: MessageCallback, context: MemoryContext, session):
    school_id = int(event.callback.payload.split(":")[1])
    await context.update_data(school_id=school_id)
    await context.set_state(OnboardingStates.subjects)
    subjects = await user_service.get_all_subjects(session)
    await context.update_data(available_subjects=subjects, selected_subjects=[])
    kb = subjects_toggle_keyboard(subjects, set())
    await event.bot.edit_message(
        message_id=event.message.body.mid,
        text="Какие предметы вы ведёте? Выберите и нажмите «Готово»:",
        attachments=[kb.as_markup()],
    )


@router.message_callback(F.callback.payload.startswith("onb_subj:"), OnboardingStates.subjects)
async def process_subject_toggle(event: MessageCallback, context: MemoryContext):
    value = event.callback.payload.split(":")[1]
    data = await context.get_data()
    selected = set(data.get("selected_subjects", []))
    subjects = data["available_subjects"]

    if value == "done":
        await context.update_data(subjects=list(selected))
        await context.set_state(OnboardingStates.phone)
        kb = contact_keyboard()
        await event.bot.edit_message(
            message_id=event.message.body.mid,
            text="Поделитесь номером телефона (нажмите кнопку или введите вручную):",
            attachments=[kb.as_markup()],
        )
        return

    subj_id = int(value)
    if subj_id in selected:
        selected.discard(subj_id)
    else:
        selected.add(subj_id)
    await context.update_data(selected_subjects=list(selected))
    kb = subjects_toggle_keyboard(subjects, selected)
    await event.bot.edit_message(
        message_id=event.message.body.mid,
        text="Какие предметы вы ведёте? Выберите и нажмите «Готово»:",
        attachments=[kb.as_markup()],
    )


@router.message_created(Contact(), OnboardingStates.phone)
async def process_phone_contact(event: MessageCreated, context: MemoryContext, contact):
    # Extract phone from contact attachment
    await context.update_data(phone=str(contact))
    await context.set_state(OnboardingStates.email)
    kb = skip_keyboard()
    await event.message.answer(
        "Введите email (или нажмите «Пропустить»):",
        attachments=[kb.as_markup()],
    )


@router.message_created(F.message.body.text, OnboardingStates.phone)
async def process_phone_text(event: MessageCreated, context: MemoryContext):
    phone = event.message.body.text.strip()
    if len(phone) < 10:
        await event.message.answer("Введите корректный номер телефона:")
        return
    await context.update_data(phone=phone)
    await context.set_state(OnboardingStates.email)
    kb = skip_keyboard()
    await event.message.answer(
        "Введите email (или нажмите «Пропустить»):",
        attachments=[kb.as_markup()],
    )


@router.message_created(F.message.body.text, OnboardingStates.email)
async def process_email(event: MessageCreated, context: MemoryContext, session):
    await context.update_data(email=event.message.body.text.strip())
    await _finish_onboarding(event, context, session, max_user_id=event.message.sender.user_id)


@router.message_callback(F.callback.payload == "onb_skip", OnboardingStates.email)
async def process_email_skip(event: MessageCallback, context: MemoryContext, session):
    await _finish_onboarding(event, context, session, max_user_id=event.callback.user.user_id)


async def _finish_onboarding(event, context: MemoryContext, session, max_user_id: int):
    data = await context.get_data()
    user_data = UserCreate(
        max_user_id=max_user_id,
        full_name=data["full_name"],
        phone=data["phone"],
        email=data.get("email"),
        region_id=data["region_id"],
        school_id=data["school_id"],
        subjects=data.get("subjects", []),
    )
    await user_service.create_user(session, user_data)
    await context.clear()
    if hasattr(event, "message") and hasattr(event.message, "answer"):
        await event.message.answer(
            "Регистрация завершена!\n\n"
            "Просто напишите, что вы ищете, и я найду подходящие уроки.",
        )
    else:
        await event.answer(new_text="Регистрация завершена!\n\n"
                                    "Просто напишите, что вы ищете, и я найду подходящие уроки.")
```

**Important:** The `BotStarted` event needs to trigger the FSM. Since `BotStarted` doesn't go through `message_created`, the handler should set the state via a separate mechanism. You may need to set state in the `bot_started` handler using `context` — verify during implementation that `MemoryContext` is injectable into `bot_started` handlers. If not, use a `/start` command handler instead.

**Step 3: Commit**

```bash
git add src/max/handlers/
git commit -m "feat: add MAX bot start & onboarding handlers"
```

---

### Task 7: MAX handlers — menu, search, param_search, admin

**Files:**
- Create: `src/max/handlers/menu.py`
- Create: `src/max/handlers/search.py`
- Create: `src/max/handlers/param_search.py`
- Create: `src/max/handlers/admin.py`

**Step 1: Create menu.py**

```python
from maxapi import F, Router
from maxapi.context import MemoryContext
from maxapi.types import MessageCallback

router = Router(router_id="max_menu")


@router.message_callback(F.callback.payload == "new_search")
async def new_search(event: MessageCallback, context: MemoryContext):
    await context.clear()
    await event.answer(new_text="Просто напишите, что вы ищете, и я найду подходящие уроки.")


@router.message_callback(F.callback.payload == "noop")
async def noop(event: MessageCallback):
    await event.answer(notification="")
```

**Step 2: Create search.py**

```python
from maxapi import F, Router
from maxapi.context import MemoryContext
from maxapi.types import MessageCallback, MessageCreated

from src.core.services.search import SearchService
from src.core.services.user import UserService
from src.max.formatters import format_text_results
from src.max.keyboards import search_pagination_keyboard

router = Router(router_id="max_search")
search_service = SearchService()
user_service = UserService()


@router.message_created(F.message.body.text)
async def handle_search(event: MessageCreated, context: MemoryContext, session):
    """Catch-all: any text message from registered user triggers search."""
    user = await user_service.get_by_max_user_id(session, event.message.sender.user_id)
    if not user:
        await event.message.answer(
            "Вы ещё не зарегистрированы. Нажмите «Начать» для регистрации."
        )
        return

    query = event.message.body.text.strip()
    if len(query) < 2:
        await event.message.answer("Слишком короткий запрос. Введите минимум 2 символа.")
        return

    await context.update_data(search_query=query)

    result = await search_service.hybrid_search(session, query, page=1)
    text = format_text_results(result)

    if result.total_pages > 0:
        kb = search_pagination_keyboard(1, result.total_pages)
        await event.message.answer(text, attachments=[kb.as_markup()])
    else:
        await event.message.answer(text)


@router.message_callback(F.callback.payload.startswith("search:page:"))
async def paginate_search(event: MessageCallback, context: MemoryContext, session):
    page = int(event.callback.payload.split(":")[-1])
    data = await context.get_data()
    query = data.get("search_query", "")

    result = await search_service.hybrid_search(session, query, page=page)
    text = format_text_results(result)
    kb = search_pagination_keyboard(page, result.total_pages)

    await event.bot.edit_message(
        message_id=event.message.body.mid,
        text=text,
        attachments=[kb.as_markup()],
    )
```

**Step 3: Create param_search.py**

```python
from maxapi import F, Router
from maxapi.context import MemoryContext
from maxapi.types import MessageCallback

from src.config import get_settings
from src.core.schemas import FilterState
from src.core.services.content import ContentService
from src.max.formatters import format_param_results
from src.max.keyboards import (
    grades_keyboard,
    items_keyboard,
    pagination_keyboard,
)

router = Router(router_id="max_param_search")
content_service = ContentService()


@router.message_callback(F.callback.payload == "search_params")
async def start_param_search(event: MessageCallback, context: MemoryContext, session):
    subjects = await content_service.get_subjects(session)
    await context.update_data(filter={})
    kb = items_keyboard(subjects, "ps_subj")
    await event.bot.edit_message(
        message_id=event.message.body.mid,
        text="Выберите предмет:",
        attachments=[kb.as_markup()],
    )


@router.message_callback(F.callback.payload.startswith("ps_subj:"))
async def select_subject(event: MessageCallback, context: MemoryContext, session):
    subject_id = int(event.callback.payload.split(":")[1])
    await context.update_data(filter={"subject_id": subject_id})
    grades = await content_service.get_grades_for_subject(session, subject_id)
    kb = grades_keyboard(grades, "ps_grade")
    await event.bot.edit_message(
        message_id=event.message.body.mid,
        text="Выберите класс:",
        attachments=[kb.as_markup()],
    )


@router.message_callback(F.callback.payload.startswith("ps_grade:"))
async def select_grade(event: MessageCallback, context: MemoryContext, session):
    grade = int(event.callback.payload.split(":")[1])
    data = await context.get_data()
    filters = data["filter"]
    filters["grade"] = grade
    await context.update_data(filter=filters)

    sections = await content_service.get_sections(session, filters["subject_id"], grade)
    if sections:
        kb = items_keyboard(sections, "ps_section", add_skip=True)
        await event.bot.edit_message(
            message_id=event.message.body.mid,
            text="Выберите раздел:",
            attachments=[kb.as_markup()],
        )
    else:
        await _show_results(event, context, session)


@router.message_callback(F.callback.payload.startswith("ps_section:"))
async def select_section(event: MessageCallback, context: MemoryContext, session):
    value = event.callback.payload.split(":")[1]
    data = await context.get_data()
    filters = data["filter"]

    if value == "skip":
        await _show_results(event, context, session)
        return

    section_id = int(value)
    filters["section_id"] = section_id
    await context.update_data(filter=filters)

    topics = await content_service.get_topics(session, filters["subject_id"], filters["grade"], section_id)
    if topics:
        kb = items_keyboard(topics, "ps_topic", add_skip=True)
        await event.bot.edit_message(
            message_id=event.message.body.mid,
            text="Выберите тему:",
            attachments=[kb.as_markup()],
        )
    else:
        await _show_results(event, context, session)


@router.message_callback(F.callback.payload.startswith("ps_topic:"))
async def select_topic(event: MessageCallback, context: MemoryContext, session):
    value = event.callback.payload.split(":")[1]
    data = await context.get_data()
    filters = data["filter"]

    if value != "skip":
        filters["topic_id"] = int(value)
        await context.update_data(filter=filters)

    await _show_results(event, context, session)


@router.message_callback(F.callback.payload.startswith("ps_results:page:"))
async def paginate_results(event: MessageCallback, context: MemoryContext, session):
    page = int(event.callback.payload.split(":")[-1])
    await _show_results(event, context, session, page=page)


async def _show_results(event: MessageCallback, context: MemoryContext, session, page=1):
    data = await context.get_data()
    filters = FilterState(**data["filter"])
    per_page = get_settings().results_per_page
    lessons, total = await content_service.get_lessons(session, filters, page=page, per_page=per_page)

    text = format_param_results(lessons)
    total_pages = -(-total // per_page)

    if total_pages > 0:
        kb = pagination_keyboard(page, total_pages, "ps_results")
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

**Step 4: Create admin.py**

```python
import asyncio
import logging

from maxapi import Router
from maxapi.types import Command, MessageCreated

from src.config import get_settings
from src.core.services.loader import (
    fetch_all_content_from_sheets,
    reload_courses_data,
    reload_lesson_links_data,
    reload_lessons_data,
    reload_schools_data,
    reload_sections_data,
    reload_subjects_data,
    reload_topics_data,
)
from src.core.services.user import UserService

router = Router(router_id="max_admin")
logger = logging.getLogger("max.admin")
user_service = UserService()


def is_admin(user_id: int) -> bool:
    return user_id in get_settings().admin_ids


def _short_error(e: Exception) -> str:
    return str(e)[:200]


@router.message_created(Command("reload"))
async def cmd_reload(event: MessageCreated, session):
    user_id = event.message.sender.user_id
    logger.info("Reload requested by max_user_id=%s", user_id)
    if not is_admin(user_id):
        await event.message.answer("У вас нет прав для этой команды.")
        return

    await event.message.answer("\u23f3 Загрузка данных...")

    try:
        schools_result = await reload_schools_data(session)
        await event.message.answer(
            f"\u2705 Регионы: {schools_result['regions']}, "
            f"Школы: {schools_result['schools']}"
        )
    except Exception as e:
        logger.exception("Failed to reload schools")
        await event.message.answer(f"\u274c Ошибка загрузки школ: {_short_error(e)}")
        return

    try:
        await event.message.answer("\u23f3 Ожидание перед загрузкой контента (квота API)...")
        await asyncio.sleep(60)
        await event.message.answer("\u23f3 Загрузка контента из Google Sheets...")
        content = fetch_all_content_from_sheets()
    except Exception as e:
        logger.exception("Failed to fetch content from sheets")
        await event.message.answer(f"\u274c Ошибка загрузки из Google Sheets: {_short_error(e)}")
        return

    try:
        subjects_result = await reload_subjects_data(session, content["subjects"])
        await event.message.answer(f"\u2705 Предметы: {subjects_result['subjects']} загружено")
    except Exception as e:
        logger.exception("Failed to reload subjects")
        await event.message.answer(f"\u274c Ошибка загрузки предметов: {_short_error(e)}")
        return

    try:
        courses_result = await reload_courses_data(session, content["courses"])
        await event.message.answer(f"\u2705 Курсы: {courses_result['courses']} загружено")
    except Exception as e:
        logger.exception("Failed to reload courses")
        await event.message.answer(f"\u274c Ошибка загрузки курсов: {_short_error(e)}")
        return

    try:
        sections_result = await reload_sections_data(session, content["sections"])
        await event.message.answer(f"\u2705 Разделы: {sections_result['sections']} загружено")
    except Exception as e:
        logger.exception("Failed to reload sections")
        await event.message.answer(f"\u274c Ошибка загрузки разделов: {_short_error(e)}")
        return

    try:
        topics_result = await reload_topics_data(session, content["topics"])
        await event.message.answer(f"\u2705 Темы: {topics_result['topics']} загружено")
    except Exception as e:
        logger.exception("Failed to reload topics")
        await event.message.answer(f"\u274c Ошибка загрузки тем: {_short_error(e)}")
        return

    try:
        lessons_result = await reload_lessons_data(session, content["lessons"])
        emb_status = "\u2705" if lessons_result["embeddings"] else "\u26a0\ufe0f без эмбеддингов"
        await event.message.answer(
            f"\u2705 Уроки: {lessons_result['loaded']} загружено, "
            f"{lessons_result['errors']} ошибок\n"
            f"Эмбеддинги: {emb_status}"
        )
        if lessons_result["error_rows"]:
            await event.message.answer(f"Строки с ошибками: {lessons_result['error_rows'][:20]}")
    except Exception as e:
        logger.exception("Failed to reload lessons")
        await event.message.answer(f"\u274c Ошибка загрузки уроков: {_short_error(e)}")
        return

    try:
        links_result = await reload_lesson_links_data(session, content["links"])
        await event.message.answer(f"\u2705 Ссылки: {links_result['links']} загружено")
    except Exception as e:
        logger.exception("Failed to reload lesson links")
        await event.message.answer(f"\u274c Ошибка загрузки ссылок: {_short_error(e)}")
        return

    await event.message.answer("\u2705 Загрузка данных завершена!")


@router.message_created(Command("stats"))
async def cmd_stats(event: MessageCreated, session):
    if not is_admin(event.message.sender.user_id):
        return
    user_count = await user_service.get_user_count(session)
    await event.message.answer(f"\U0001f4ca Статистика:\n\nПользователей: {user_count}")
```

**Step 5: Commit**

```bash
git add src/max/handlers/
git commit -m "feat: add MAX bot menu, search, param_search, admin handlers"
```

---

### Task 8: Update main.py — dual bot launch

**Files:**
- Modify: `src/main.py`

**Step 1: Rewrite main.py**

```python
import asyncio
import logging

from aiogram.types import MenuButtonWebApp, WebAppInfo

from src.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def start_telegram():
    from src.telegram.bot import create_bot, create_dispatcher
    from src.telegram.handlers import register_all_routers
    from src.telegram.middlewares import DatabaseMiddleware

    settings = get_settings()
    bot = create_bot()
    dp = create_dispatcher()
    dp.update.middleware(DatabaseMiddleware())
    register_all_routers(dp)

    if settings.web_app_url:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Регистрация",
                web_app=WebAppInfo(url=settings.web_app_url),
            )
        )
        logger.info("Telegram MenuButton set to Web App: %s", settings.web_app_url)

    logger.info("Telegram bot starting polling...")
    await dp.start_polling(bot)


async def start_max():
    from src.max.bot import create_max_bot, create_max_dispatcher
    from src.max.handlers import register_all_routers
    from src.max.middlewares import DatabaseMiddleware

    bot = create_max_bot()
    dp = create_max_dispatcher()
    dp.middleware(DatabaseMiddleware())
    register_all_routers(dp)

    logger.info("MAX bot starting polling...")
    await dp.start_polling(bot)


async def main():
    settings = get_settings()
    tasks = []

    if settings.enable_telegram:
        tasks.append(start_telegram())
        logger.info("Telegram bot enabled")
    else:
        logger.info("Telegram bot disabled")

    if settings.enable_max:
        if not settings.max_bot_token:
            logger.warning("MAX bot enabled but MAX_BOT_TOKEN not set, skipping")
        else:
            tasks.append(start_max())
            logger.info("MAX bot enabled")
    else:
        logger.info("MAX bot disabled")

    if not tasks:
        logger.error("No bots enabled, exiting")
        return

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
```

**Step 2: Commit**

```bash
git add src/main.py
git commit -m "feat: dual bot launcher — Telegram + MAX with enable/disable flags"
```

---

### Task 9: Web App auth — MAX support

**Files:**
- Modify: `src/web/auth.py`
- Modify: `src/web/routes.py`

**Step 1: Add MAX validation to auth.py**

Add `validate_max_init_data` function and `get_platform_user` dependency:

```python
# Add after existing validate_init_data function:

def validate_max_init_data(init_data: str, bot_token: str) -> dict:
    """Validate MAX WebApp initData and return parsed data.

    MAX uses the same HMAC-SHA256 validation scheme as Telegram.
    Verify during implementation — adjust if MAX differs.
    """
    # MAX Mini Apps use the same validation as Telegram WebApp
    return validate_init_data(init_data, bot_token)


async def get_platform_user(
    x_telegram_init_data: str | None = Header(default=None),
    x_max_init_data: str | None = Header(default=None),
) -> dict:
    """FastAPI dependency: validate initData from either platform."""
    settings = get_settings()

    if x_telegram_init_data:
        try:
            user_data = validate_init_data(x_telegram_init_data, settings.bot_token)
            user_data["platform"] = "telegram"
            return user_data
        except (ValueError, KeyError) as e:
            raise HTTPException(status_code=401, detail=str(e))

    if x_max_init_data:
        try:
            user_data = validate_max_init_data(x_max_init_data, settings.max_bot_token)
            user_data["platform"] = "max"
            return user_data
        except (ValueError, KeyError) as e:
            raise HTTPException(status_code=401, detail=str(e))

    raise HTTPException(status_code=401, detail="No auth header provided")
```

**Step 2: Update routes.py to use platform-aware auth**

Replace `get_telegram_user` dependency with `get_platform_user`:

```python
from src.web.auth import get_platform_user

# In /auth endpoint:
@router.post("/auth")
async def auth(
    user: dict = Depends(get_platform_user),
    session: AsyncSession = Depends(get_session),
):
    platform = user.get("platform", "telegram")
    user_id = user["id"]

    if platform == "max":
        db_user = await user_service.get_by_max_user_id(session, user_id)
    else:
        db_user = await user_service.get_by_telegram_id(session, user_id)

    return {
        "user_id": user_id,
        "platform": platform,
        "status": "existing" if db_user else "new",
        "full_name": db_user.full_name if db_user else None,
    }

# In /register endpoint:
@router.post("/register")
async def register(
    data: UserCreate,
    user: dict = Depends(get_platform_user),
    session: AsyncSession = Depends(get_session),
):
    platform = user.get("platform", "telegram")
    if platform == "max":
        data.max_user_id = user["id"]
        data.telegram_id = None
    else:
        data.telegram_id = user["id"]
        data.max_user_id = None
    db_user = await user_service.create_user(session, data)
    return {"ok": True, "user_id": db_user.id}
```

The `/regions`, `/schools`, `/subjects` endpoints only need auth — no platform-specific logic, so just swap the dependency.

**Step 3: Commit**

```bash
git add src/web/auth.py src/web/routes.py
git commit -m "feat: web app auth supports both Telegram and MAX platforms"
```

---

### Task 10: Smoke test & verification

**Step 1: Verify imports resolve**

Run: `python -c "from src.max.handlers import register_all_routers; print('OK')"`
Expected: `OK`

**Step 2: Verify migration applies**

Run: `alembic upgrade head`
Expected: migration applies without errors

**Step 3: Run existing tests**

Run: `pytest tests/ -v`
Expected: all existing tests pass (no regressions)

**Step 4: Test MAX bot startup (if token available)**

Run: `ENABLE_TELEGRAM=false python -m src.main`
Expected: `MAX bot starting polling...` in logs

**Step 5: Final commit if any fixups needed**

```bash
git add -A
git commit -m "fix: address smoke test issues"
```
