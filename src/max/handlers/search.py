from maxapi import F, Router
from maxapi.context import MemoryContext
from maxapi.types import MessageCallback, MessageCreated
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.core.schemas import ClarifyResult, LessonResult, SearchResult
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

    text = format_text_results(result)
    if result.total_pages > 0:
        kb = search_pagination_keyboard(1, result.total_pages)
        await event.message.answer(text, attachments=[kb.as_markup()])
    else:
        await event.message.answer(text)


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
