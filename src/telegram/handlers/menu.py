from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from src.telegram.keyboards import search_choice_keyboard

router = Router()


@router.callback_query(F.data == "new_search")
async def new_search(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    # Freeze the old message (remove keyboard), send new one
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "Выберите способ поиска:",
        reply_markup=search_choice_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "search_text")
async def search_text(callback: CallbackQuery, state: FSMContext):
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
