from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from src.core.services.user import UserService
from src.telegram.keyboards import search_choice_keyboard

router = Router()
user_service = UserService()


@router.callback_query(F.data == "new_search")
async def new_search(callback: CallbackQuery, state: FSMContext, session):
    user = await user_service.get_by_telegram_id(session, callback.from_user.id)
    if user and not user.consent_given:
        await callback.message.edit_text(
            "Для использования поиска необходимо дать согласие на обработку персональных данных.\n\n"
            "Нажмите /start, чтобы получить запрос на согласие повторно."
        )
        await callback.answer()
        return
    await state.clear()
    # Freeze the old message (remove keyboard), send new one
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "Выберите способ поиска:",
        reply_markup=search_choice_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "search_text")
async def search_text(callback: CallbackQuery, state: FSMContext, session):
    user = await user_service.get_by_telegram_id(session, callback.from_user.id)
    if user and not user.consent_given:
        await callback.message.edit_text(
            "Для использования поиска необходимо дать согласие на обработку персональных данных.\n\n"
            "Нажмите /start, чтобы получить запрос на согласие повторно."
        )
        await callback.answer()
        return
    await state.clear()
    # Freeze the old message (remove keyboard), send new one
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "Просто напишите, что вы ищете, и я найду подходящие уроки."
    )
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()
