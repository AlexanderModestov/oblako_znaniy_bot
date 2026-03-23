from maxapi import F, Router
from maxapi.context import MemoryContext
from maxapi.types import MessageCallback

from src.config import get_settings
from src.core.schemas import FilterState
from src.core.services.content import ContentService
from src.max.formatters import format_param_results
from src.max.keyboards import (
    grades_keyboard,
    items_keyboard,
    pagination_keyboard,
)

router = Router(router_id="max_param_search")
content_service = ContentService()


@router.message_callback(F.callback.payload == "search_params")
async def start_param_search(event: MessageCallback, context: MemoryContext, session):
    subjects = await content_service.get_subjects(session)
    await context.update_data(filter={})
    kb = items_keyboard(subjects, "ps_subj")
    await event.bot.edit_message(
        message_id=event.message.body.mid,
        text="Выберите предмет:",
        attachments=[kb.as_markup()],
    )


@router.message_callback(F.callback.payload.startswith("ps_subj:"))
async def select_subject(event: MessageCallback, context: MemoryContext, session):
    subject_id = int(event.callback.payload.split(":")[1])
    await context.update_data(filter={"subject_id": subject_id})
    grades = await content_service.get_grades_for_subject(session, subject_id)
    kb = grades_keyboard(grades, "ps_grade")
    await event.bot.edit_message(
        message_id=event.message.body.mid,
        text="Выберите класс:",
        attachments=[kb.as_markup()],
    )


@router.message_callback(F.callback.payload.startswith("ps_grade:"))
async def select_grade(event: MessageCallback, context: MemoryContext, session):
    grade = int(event.callback.payload.split(":")[1])
    data = await context.get_data()
    filters = data["filter"]
    filters["grade"] = grade
    await context.update_data(filter=filters)

    sections = await content_service.get_sections(session, filters["subject_id"], grade)
    if sections:
        kb = items_keyboard(sections, "ps_section", add_skip=True)
        await event.bot.edit_message(
            message_id=event.message.body.mid,
            text="Выберите раздел:",
            attachments=[kb.as_markup()],
        )
    else:
        await _show_results(event, context, session)


@router.message_callback(F.callback.payload.startswith("ps_section:"))
async def select_section(event: MessageCallback, context: MemoryContext, session):
    value = event.callback.payload.split(":")[1]
    data = await context.get_data()
    filters = data["filter"]

    if value == "skip":
        await _show_results(event, context, session)
        return

    section_id = int(value)
    filters["section_id"] = section_id
    await context.update_data(filter=filters)

    topics = await content_service.get_topics(session, filters["subject_id"], filters["grade"], section_id)
    if topics:
        kb = items_keyboard(topics, "ps_topic", add_skip=True)
        await event.bot.edit_message(
            message_id=event.message.body.mid,
            text="Выберите тему:",
            attachments=[kb.as_markup()],
        )
    else:
        await _show_results(event, context, session)


@router.message_callback(F.callback.payload.startswith("ps_topic:"))
async def select_topic(event: MessageCallback, context: MemoryContext, session):
    value = event.callback.payload.split(":")[1]
    data = await context.get_data()
    filters = data["filter"]

    if value != "skip":
        filters["topic_id"] = int(value)
        await context.update_data(filter=filters)

    await _show_results(event, context, session)


@router.message_callback(F.callback.payload.startswith("ps_results:page:"))
async def paginate_results(event: MessageCallback, context: MemoryContext, session):
    page = int(event.callback.payload.split(":")[-1])
    await _show_results(event, context, session, page=page)


async def _show_results(event: MessageCallback, context: MemoryContext, session, page=1):
    data = await context.get_data()
    filters = FilterState(**data["filter"])
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
