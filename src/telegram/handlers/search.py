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
