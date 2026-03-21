from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from src.config import get_settings
from src.core.schemas import FilterState
from src.core.services.content import ContentService
from src.telegram.formatters import format_param_results
from src.telegram.keyboards import (
    grades_keyboard,
    items_keyboard,
    pagination_keyboard,
)

router = Router()
content_service = ContentService()


@router.callback_query(F.data == "search_params")
async def start_param_search(callback: CallbackQuery, state: FSMContext, session):
    subjects = await content_service.get_subjects(session)
    await state.update_data(filter={})
    await callback.message.edit_text(
        "Выберите предмет:",
        reply_markup=items_keyboard(subjects, "ps_subj"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ps_subj:"))
async def select_subject(callback: CallbackQuery, state: FSMContext, session):
    subject_id = int(callback.data.split(":")[1])
    await state.update_data(filter={"subject_id": subject_id})
    grades = await content_service.get_grades_for_subject(session, subject_id)
    await callback.message.edit_text(
        "Выберите класс:",
        reply_markup=grades_keyboard(grades, "ps_grade"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ps_grade:"))
async def select_grade(callback: CallbackQuery, state: FSMContext, session):
    grade = int(callback.data.split(":")[1])
    data = await state.get_data()
    filters = data["filter"]
    filters["grade"] = grade
    await state.update_data(filter=filters)

    sections = await content_service.get_sections(session, filters["subject_id"], grade)
    if sections:
        section_items = [{"name": s} for s in sections]
        await callback.message.edit_text(
            "Выберите раздел:",
            reply_markup=items_keyboard(section_items, "ps_section", add_skip=True),
        )
    else:
        await _show_results(callback, state, session)
    await callback.answer()


@router.callback_query(F.data.startswith("ps_section:"))
async def select_section(callback: CallbackQuery, state: FSMContext, session):
    value = callback.data.split(":")[1]
    data = await state.get_data()
    filters = data["filter"]

    if value == "skip":
        await _show_results(callback, state, session)
        await callback.answer()
        return

    filters["section"] = value
    await state.update_data(filter=filters)

    topics = await content_service.get_topics(session, filters["subject_id"], filters["grade"], value)
    if topics:
        topic_items = [{"name": t} for t in topics]
        await callback.message.edit_text(
            "Выберите тему:",
            reply_markup=items_keyboard(topic_items, "ps_topic", add_skip=True),
        )
    else:
        await _show_results(callback, state, session)
    await callback.answer()


@router.callback_query(F.data.startswith("ps_topic:"))
async def select_topic(callback: CallbackQuery, state: FSMContext, session):
    value = callback.data.split(":")[1]
    data = await state.get_data()
    filters = data["filter"]

    if value != "skip":
        filters["topic"] = value
        await state.update_data(filter=filters)

    await _show_results(callback, state, session)
    await callback.answer()


@router.callback_query(F.data.startswith("ps_results:page:"))
async def paginate_results(callback: CallbackQuery, state: FSMContext, session):
    page = int(callback.data.split(":")[-1])
    await _show_results(callback, state, session, page=page)
    await callback.answer()


async def _show_results(callback, state, session, page=1):
    data = await state.get_data()
    filters = FilterState(**data["filter"])
    per_page = get_settings().results_per_page
    lessons, total = await content_service.get_lessons(session, filters, page=page, per_page=per_page)

    text = format_param_results(lessons)
    total_pages = -(-total // per_page)  # ceil division

    keyboard = None
    if total_pages > 0:
        keyboard = pagination_keyboard(page, total_pages, "ps_results")

    await callback.message.edit_text(text, reply_markup=keyboard)
