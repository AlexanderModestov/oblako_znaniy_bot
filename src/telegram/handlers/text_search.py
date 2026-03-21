from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from src.core.services.search import SearchService
from src.telegram.formatters import format_text_results
from src.telegram.keyboards import pagination_keyboard

router = Router()


class TextSearchStates(StatesGroup):
    waiting_query = State()


def _get_search_service():
    return SearchService()


@router.callback_query(F.data == "search_text")
async def start_text_search(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TextSearchStates.waiting_query)
    await callback.message.edit_text("Введите ключевое слово или фразу для поиска:")
    await callback.answer()


@router.message(TextSearchStates.waiting_query, F.text)
async def process_text_query(message: Message, state: FSMContext, session):
    query = message.text.strip()
    if len(query) < 2:
        await message.answer("Слишком короткий запрос. Введите минимум 2 символа:")
        return

    await state.update_data(search_query=query)
    await state.set_state(None)

    search_service = _get_search_service()
    result = await search_service.hybrid_search(session, query, page=1)
    text = format_text_results(result)

    keyboard = None
    if result.total_pages > 0:
        keyboard = pagination_keyboard(1, result.total_pages, "ts_results")

    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("ts_results:page:"))
async def paginate_text_results(callback: CallbackQuery, state: FSMContext, session):
    page = int(callback.data.split(":")[-1])
    data = await state.get_data()
    query = data.get("search_query", "")

    search_service = _get_search_service()
    result = await search_service.hybrid_search(session, query, page=page)
    text = format_text_results(result)
    keyboard = pagination_keyboard(page, result.total_pages, "ts_results")

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()
