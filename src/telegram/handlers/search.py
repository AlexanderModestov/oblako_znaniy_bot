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
from src.core.schemas import ClarifyResult, LessonResult, SearchResult
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

    text = format_text_results(result)
    keyboard = None
    if result.total_pages > 0:
        keyboard = search_pagination_keyboard(1, result.total_pages)
    await message.answer(text, reply_markup=keyboard)


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
