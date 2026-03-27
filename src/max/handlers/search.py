from maxapi import F, Router
from maxapi.context import MemoryContext
from maxapi.types import MessageCallback, MessageCreated
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.core.services.search import SearchService
from src.core.services.user import UserService
from src.max.formatters import format_text_results
from src.max.keyboards import registration_keyboard, search_pagination_keyboard

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

    await context.update_data(search_query=query)

    result = await search_service.hybrid_search(session, query, page=1)
    text = format_text_results(result)

    if result.total_pages > 0:
        kb = search_pagination_keyboard(1, result.total_pages)
        await event.message.answer(text, attachments=[kb.as_markup()])
    else:
        await event.message.answer(text)


@router.message_callback(F.callback.payload.startswith("search:page:"))
async def paginate_search(event: MessageCallback, context: MemoryContext, session: AsyncSession):
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
