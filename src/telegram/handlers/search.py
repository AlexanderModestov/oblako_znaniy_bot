import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

logger = logging.getLogger(__name__)

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
    if not query:
        await callback.answer("Нет активного поиска.", show_alert=True)
        return
    current_level = data.get("search_level", 1)
    new_level = min(current_level + 1, 2)
    try:
        await _run_search(callback=callback, state=state, session=session, query=query, level=new_level, edit=True)
    finally:
        await callback.answer()


async def _safe_edit(callback: CallbackQuery, text: str, keyboard):
    """Edit message, silently ignore 'message is not modified' error."""
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise


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
        clarify_history=[],
    )

    clarification = search_service.check_clarification(all_lessons)
    if clarification:
        await state.update_data(clarify_result=clarification.model_dump())
        options = [o.model_dump() for o in clarification.options]
        keyboard = clarify_keyboard(options, clarification.level)
        if edit and callback:
            await _safe_edit(callback, clarification.message, keyboard)
        else:
            await message.answer(clarification.message, reply_markup=keyboard)
        return

    per_page = search_service.per_page
    page_lessons = all_lessons[:per_page]
    total = len(all_lessons)
    result = SearchResult(query=query, lessons=page_lessons, total=total, page=1, per_page=per_page)
    text = format_text_results(result)
    if level == 2:
        text += "\n\n\U0001f50e Расширенный поиск (семантика)"
    total_pages = max(result.total_pages, 1)
    keyboard = search_pagination_keyboard(1, total_pages, level)

    if edit and callback:
        await _safe_edit(callback, text, keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "clarify:back")
async def handle_clarify_back(callback: CallbackQuery, state: FSMContext, session):
    """Go back: pop previous clarification step, or show raw results if at first step."""
    data = await state.get_data()
    query = data.get("search_query", "")
    search_level = data.get("search_level", 1)
    history = data.get("clarify_history", [])

    if not query:
        await callback.answer()
        return

    if history:
        # Pop the last entry, restore previous clarification
        previous = history[-1]
        new_history = history[:-1]
        prev_lessons_raw = previous.get("lessons", [])
        prev_clarify = previous.get("clarify_result") or {}

        await state.update_data(
            search_all_lessons=prev_lessons_raw,
            clarify_result=prev_clarify if prev_clarify else None,
            clarify_history=new_history,
            search_filtered=None,
        )

        options = prev_clarify.get("options", [])
        prev_level = prev_clarify.get("level", "subject")
        keyboard = clarify_keyboard(options, prev_level)
        await _safe_edit(callback, prev_clarify.get("message", ""), keyboard)
        await callback.answer()
        return

    # No history — show raw results at current level (bypass clarification)
    all_lessons_raw = data.get("search_all_lessons", [])
    all_lessons = [LessonResult(**l) for l in all_lessons_raw]
    per_page = search_service.per_page
    page_lessons = all_lessons[:per_page]
    total = len(all_lessons)
    result = SearchResult(query=query, lessons=page_lessons, total=total, page=1, per_page=per_page)
    text = format_text_results(result)
    if search_level == 2:
        text += "\n\n\U0001f50e Расширенный поиск (семантика)"
    total_pages = max(result.total_pages, 1)
    keyboard = search_pagination_keyboard(1, total_pages, search_level)

    await state.update_data(clarify_result=None, search_filtered=None)
    await _safe_edit(callback, text, keyboard)
    await callback.answer()


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
    history = data.get("clarify_history", [])

    # Push current state onto history stack before filtering
    history = history + [{
        "lessons": data.get("search_all_lessons", []),
        "clarify_result": clarify_data,
    }]

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
            clarify_history=history,
        )
        options = [o.model_dump() for o in next_clarification.options]
        keyboard = clarify_keyboard(options, next_clarification.level)
        await _safe_edit(callback, next_clarification.message, keyboard)
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
        clarify_history=history,
    )

    keyboard = search_pagination_keyboard(1, search_result.total_pages, search_level) if search_result.total_pages > 0 else None
    await _safe_edit(callback, text, keyboard)
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
