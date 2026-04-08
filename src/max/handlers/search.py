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
    if not query:
        return
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
    field_name = parts[1]
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
        filtered = [
            l for l in all_lessons
            if str(getattr(l, field_name) or "") == selected_value
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
