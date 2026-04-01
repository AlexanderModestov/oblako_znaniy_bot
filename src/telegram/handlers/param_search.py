from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from src.config import get_settings
from src.core.schemas import FilterState
from src.core.services.content import ContentService
from src.core.services.user import UserService
from src.telegram.formatters import format_param_results, format_topic_lessons
from src.telegram.keyboards import (
    grades_keyboard,
    items_keyboard,
    new_search_keyboard,
    pagination_keyboard,
    search_choice_keyboard,
)

router = Router()
content_service = ContentService()
user_service = UserService()


@router.callback_query(F.data == "search_curriculum")
async def start_param_search(callback: CallbackQuery, state: FSMContext, session):
    user = await user_service.get_by_telegram_id(session, callback.from_user.id)
    if user and not user.consent_given:
        await callback.message.edit_text(
            "Для использования поиска необходимо дать согласие на обработку персональных данных.\n\n"
            "Нажмите /start, чтобы получить запрос на согласие повторно."
        )
        await callback.answer()
        return
    subjects = await content_service.get_subjects(session)
    await state.update_data(filter={})
    await callback.message.edit_text(
        "Выберите предмет:",
        reply_markup=items_keyboard(subjects, "ps_subj", back_callback="ps_back:menu"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ps_subj:"))
async def select_subject(callback: CallbackQuery, state: FSMContext, session):
    subject_id = int(callback.data.split(":")[1])
    await state.update_data(filter={"subject_id": subject_id})
    grades = await content_service.get_grades_for_subject(session, subject_id)
    await callback.message.edit_text(
        "Выберите класс:",
        reply_markup=grades_keyboard(grades, "ps_grade", back_callback="ps_back:subjects"),
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
        await state.update_data(ps_sections=sections)
        await callback.message.edit_text(
            "Выберите раздел:",
            reply_markup=items_keyboard(sections, "ps_section", add_skip=True, back_callback="ps_back:grades"),
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

    # Look up section name by index
    sections = data.get("ps_sections", [])
    section_idx = int(value)
    section_name = sections[section_idx]["name"]
    filters["section"] = section_name
    await state.update_data(filter=filters)

    topics = await content_service.get_topics(session, filters["subject_id"], filters["grade"], section_name)
    if topics:
        await state.update_data(ps_topics=topics)
        await callback.message.edit_text(
            "Выберите тему:",
            reply_markup=items_keyboard(topics, "ps_topic", add_skip=True, back_callback="ps_back:sections"),
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
        # Look up topic name by index
        topics = data.get("ps_topics", [])
        topic_idx = int(value)
        filters["topic"] = topics[topic_idx]["name"]
        await state.update_data(filter=filters)

    await _show_results(callback, state, session)
    await callback.answer()


# --- Back navigation ---


@router.callback_query(F.data == "ps_back:menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Выберите способ поиска:",
        reply_markup=search_choice_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "ps_back:subjects")
async def back_to_subjects(callback: CallbackQuery, state: FSMContext, session):
    subjects = await content_service.get_subjects(session)
    await state.update_data(filter={})
    await callback.message.edit_text(
        "Выберите предмет:",
        reply_markup=items_keyboard(subjects, "ps_subj", back_callback="ps_back:menu"),
    )
    await callback.answer()


@router.callback_query(F.data == "ps_back:grades")
async def back_to_grades(callback: CallbackQuery, state: FSMContext, session):
    data = await state.get_data()
    subject_id = data["filter"]["subject_id"]
    grades = await content_service.get_grades_for_subject(session, subject_id)
    # Reset grade and below
    await state.update_data(filter={"subject_id": subject_id})
    await callback.message.edit_text(
        "Выберите класс:",
        reply_markup=grades_keyboard(grades, "ps_grade", back_callback="ps_back:subjects"),
    )
    await callback.answer()


@router.callback_query(F.data == "ps_back:sections")
async def back_to_sections(callback: CallbackQuery, state: FSMContext, session):
    data = await state.get_data()
    filters = data["filter"]
    sections = await content_service.get_sections(session, filters["subject_id"], filters["grade"])
    await state.update_data(
        ps_sections=sections,
        filter={"subject_id": filters["subject_id"], "grade": filters["grade"]},
    )
    await callback.message.edit_text(
        "Выберите раздел:",
        reply_markup=items_keyboard(sections, "ps_section", add_skip=True, back_callback="ps_back:grades"),
    )
    await callback.answer()


# --- Pagination & results ---


@router.callback_query(F.data.startswith("ps_results:page:"))
async def paginate_results(callback: CallbackQuery, state: FSMContext, session):
    page = int(callback.data.split(":")[-1])
    await _show_results(callback, state, session, page=page)
    await callback.answer()


async def _show_results(callback, state, session, page=1):
    data = await state.get_data()
    filters = FilterState(**data["filter"])

    # If topic is selected, show all lessons at once
    if filters.topic:
        lessons = await content_service.get_all_lessons(session, filters)
        text = format_topic_lessons(lessons)
        await callback.message.edit_text(text, reply_markup=new_search_keyboard())
        return

    per_page = get_settings().results_per_page
    lessons, total = await content_service.get_lessons(session, filters, page=page, per_page=per_page)

    text = format_param_results(lessons)
    total_pages = -(-total // per_page)  # ceil division

    keyboard = None
    if total_pages > 0:
        keyboard = pagination_keyboard(page, total_pages, "ps_results")

    await callback.message.edit_text(text, reply_markup=keyboard)
