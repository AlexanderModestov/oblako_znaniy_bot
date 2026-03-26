from maxapi import F, Router
from maxapi.context import MemoryContext
from maxapi.types import MessageCallback
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.core.schemas import FilterState
from src.core.services.content import ContentService
from src.max.formatters import format_param_results, format_topic_lessons
from src.max.keyboards import (
    grades_keyboard,
    items_keyboard,
    new_search_keyboard,
    pagination_keyboard,
    search_choice_keyboard,
)

router = Router(router_id="max_param_search")
content_service = ContentService()


@router.message_callback(F.callback.payload == "search_curriculum")
async def start_param_search(event: MessageCallback, context: MemoryContext, session: AsyncSession):
    subjects = await content_service.get_subjects(session)
    await context.update_data(filter={})
    kb = items_keyboard(subjects, "ps_subj", back_callback="ps_back:menu")
    await event.bot.edit_message(
        message_id=event.message.body.mid,
        text="Выберите предмет:",
        attachments=[kb.as_markup()],
    )


@router.message_callback(F.callback.payload.startswith("ps_subj:"))
async def select_subject(event: MessageCallback, context: MemoryContext, session: AsyncSession):
    subject_id = int(event.callback.payload.split(":")[1])
    await context.update_data(filter={"subject_id": subject_id})
    grades = await content_service.get_grades_for_subject(session, subject_id)
    kb = grades_keyboard(grades, "ps_grade", back_callback="ps_back:subjects")
    await event.bot.edit_message(
        message_id=event.message.body.mid,
        text="Выберите класс:",
        attachments=[kb.as_markup()],
    )


@router.message_callback(F.callback.payload.startswith("ps_grade:"))
async def select_grade(event: MessageCallback, context: MemoryContext, session: AsyncSession):
    grade = int(event.callback.payload.split(":")[1])
    data = await context.get_data()
    filters = data["filter"]
    filters["grade"] = grade
    await context.update_data(filter=filters)

    sections = await content_service.get_sections(session, filters["subject_id"], grade)
    if sections:
        await context.update_data(ps_sections=sections)
        kb = items_keyboard(sections, "ps_section", add_skip=True, back_callback="ps_back:grades")
        await event.bot.edit_message(
            message_id=event.message.body.mid,
            text="Выберите раздел:",
            attachments=[kb.as_markup()],
        )
    else:
        await _show_results(event, context, session: AsyncSession)


@router.message_callback(F.callback.payload.startswith("ps_section:"))
async def select_section(event: MessageCallback, context: MemoryContext, session: AsyncSession):
    value = event.callback.payload.split(":")[1]
    data = await context.get_data()
    filters = data["filter"]

    if value == "skip":
        await _show_results(event, context, session: AsyncSession)
        return

    # Look up section name by index
    sections = data.get("ps_sections", [])
    section_name = sections[int(value)]["name"]
    filters["section"] = section_name
    await context.update_data(filter=filters)

    topics = await content_service.get_topics(session, filters["subject_id"], filters["grade"], section_name)
    if topics:
        await context.update_data(ps_topics=topics)
        kb = items_keyboard(topics, "ps_topic", add_skip=True, back_callback="ps_back:sections")
        await event.bot.edit_message(
            message_id=event.message.body.mid,
            text="Выберите тему:",
            attachments=[kb.as_markup()],
        )
    else:
        await _show_results(event, context, session: AsyncSession)


@router.message_callback(F.callback.payload.startswith("ps_topic:"))
async def select_topic(event: MessageCallback, context: MemoryContext, session: AsyncSession):
    value = event.callback.payload.split(":")[1]
    data = await context.get_data()
    filters = data["filter"]

    if value != "skip":
        # Look up topic name by index
        topics = data.get("ps_topics", [])
        filters["topic"] = topics[int(value)]["name"]
        await context.update_data(filter=filters)

    await _show_results(event, context, session: AsyncSession)


# --- Back navigation ---


@router.message_callback(F.callback.payload == "ps_back:menu")
async def back_to_menu(event: MessageCallback, context: MemoryContext):
    await context.clear()
    kb = search_choice_keyboard()
    await event.bot.edit_message(
        message_id=event.message.body.mid,
        text="Выберите способ поиска:",
        attachments=[kb.as_markup()],
    )


@router.message_callback(F.callback.payload == "ps_back:subjects")
async def back_to_subjects(event: MessageCallback, context: MemoryContext, session: AsyncSession):
    subjects = await content_service.get_subjects(session)
    await context.update_data(filter={})
    kb = items_keyboard(subjects, "ps_subj", back_callback="ps_back:menu")
    await event.bot.edit_message(
        message_id=event.message.body.mid,
        text="Выберите предмет:",
        attachments=[kb.as_markup()],
    )


@router.message_callback(F.callback.payload == "ps_back:grades")
async def back_to_grades(event: MessageCallback, context: MemoryContext, session: AsyncSession):
    data = await context.get_data()
    subject_id = data["filter"]["subject_id"]
    grades = await content_service.get_grades_for_subject(session, subject_id)
    await context.update_data(filter={"subject_id": subject_id})
    kb = grades_keyboard(grades, "ps_grade", back_callback="ps_back:subjects")
    await event.bot.edit_message(
        message_id=event.message.body.mid,
        text="Выберите класс:",
        attachments=[kb.as_markup()],
    )


@router.message_callback(F.callback.payload == "ps_back:sections")
async def back_to_sections(event: MessageCallback, context: MemoryContext, session: AsyncSession):
    data = await context.get_data()
    filters = data["filter"]
    sections = await content_service.get_sections(session, filters["subject_id"], filters["grade"])
    await context.update_data(
        ps_sections=sections,
        filter={"subject_id": filters["subject_id"], "grade": filters["grade"]},
    )
    kb = items_keyboard(sections, "ps_section", add_skip=True, back_callback="ps_back:grades")
    await event.bot.edit_message(
        message_id=event.message.body.mid,
        text="Выберите раздел:",
        attachments=[kb.as_markup()],
    )


# --- Pagination & results ---


@router.message_callback(F.callback.payload.startswith("ps_results:page:"))
async def paginate_results(event: MessageCallback, context: MemoryContext, session: AsyncSession):
    page = int(event.callback.payload.split(":")[-1])
    await _show_results(event, context, session, page=page)


async def _show_results(event: MessageCallback, context: MemoryContext, session, page=1):
    data = await context.get_data()
    filters = FilterState(**data["filter"])

    # If topic is selected, show all lessons at once
    if filters.topic:
        lessons = await content_service.get_all_lessons(session, filters)
        text = format_topic_lessons(lessons)
        kb = new_search_keyboard()
        await event.bot.edit_message(
            message_id=event.message.body.mid,
            text=text,
            attachments=[kb.as_markup()],
        )
        return

    per_page = get_settings().results_per_page
    lessons, total = await content_service.get_lessons(session, filters, page=page, per_page=per_page)

    text = format_param_results(lessons)
    total_pages = -(-total // per_page)

    if total_pages > 0:
        kb = pagination_keyboard(page, total_pages, "ps_results")
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
