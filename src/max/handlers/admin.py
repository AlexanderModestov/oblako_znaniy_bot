import asyncio
import logging

from maxapi import Router
from maxapi.types import Command, MessageCreated
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.core.services.loader import (
    fetch_all_content_from_sheets,
    reload_courses_data,
    reload_lesson_links_data,
    reload_lessons_data,
    reload_schools_data,
    reload_sections_data,
    reload_subjects_data,
    reload_topics_data,
)
from src.core.services.user import UserService

router = Router(router_id="max_admin")
logger = logging.getLogger("max.admin")
user_service = UserService()


def is_admin(user_id: int) -> bool:
    return user_id in get_settings().admin_ids


def _short_error(e: Exception) -> str:
    return str(e)[:200]


@router.message_created(Command("reload"))
async def cmd_reload(event: MessageCreated, session: AsyncSession):
    user_id = event.message.sender.user_id
    logger.info("Reload requested by max_user_id=%s", user_id)
    if not is_admin(user_id):
        await event.message.answer("У вас нет прав для этой команды.")
        return

    await event.message.answer("\u23f3 Загрузка данных...")

    try:
        schools_result = await reload_schools_data(session)
        await event.message.answer(
            f"\u2705 Регионы: {schools_result['regions']}, "
            f"Школы: {schools_result['schools']}\n"
            f"Строк: {schools_result['rows_total']}, "
            f"с муниципалитетом: {schools_result['has_municipality']}"
        )
    except Exception as e:
        logger.exception("Failed to reload schools")
        await event.message.answer(f"\u274c Ошибка загрузки школ: {_short_error(e)}")
        return

    try:
        await event.message.answer("\u23f3 Ожидание перед загрузкой контента (квота API)...")
        await asyncio.sleep(60)
        await event.message.answer("\u23f3 Загрузка контента из Google Sheets...")
        content = fetch_all_content_from_sheets()
    except Exception as e:
        logger.exception("Failed to fetch content from sheets")
        await event.message.answer(f"\u274c Ошибка загрузки из Google Sheets: {_short_error(e)}")
        return

    try:
        subjects_result = await reload_subjects_data(session, content["subjects"])
        await event.message.answer(f"\u2705 Предметы: {subjects_result['subjects']} загружено")
    except Exception as e:
        logger.exception("Failed to reload subjects")
        await event.message.answer(f"\u274c Ошибка загрузки предметов: {_short_error(e)}")
        return

    try:
        courses_result = await reload_courses_data(session, content["courses"])
        await event.message.answer(f"\u2705 Курсы: {courses_result['courses']} загружено")
    except Exception as e:
        logger.exception("Failed to reload courses")
        await event.message.answer(f"\u274c Ошибка загрузки курсов: {_short_error(e)}")
        return

    try:
        sections_result = await reload_sections_data(session, content["sections"])
        await event.message.answer(f"\u2705 Разделы: {sections_result['sections']} загружено")
    except Exception as e:
        logger.exception("Failed to reload sections")
        await event.message.answer(f"\u274c Ошибка загрузки разделов: {_short_error(e)}")
        return

    try:
        topics_result = await reload_topics_data(session, content["topics"])
        await event.message.answer(f"\u2705 Темы: {topics_result['topics']} загружено")
    except Exception as e:
        logger.exception("Failed to reload topics")
        await event.message.answer(f"\u274c Ошибка загрузки тем: {_short_error(e)}")
        return

    try:
        lessons_result = await reload_lessons_data(session, content["lessons"])
        emb_status = "\u2705" if lessons_result["embeddings"] else "\u26a0\ufe0f без эмбеддингов"
        await event.message.answer(
            f"\u2705 Уроки: {lessons_result['loaded']} загружено, "
            f"{lessons_result['errors']} ошибок\n"
            f"Эмбеддинги: {emb_status}"
        )
        if lessons_result["error_rows"]:
            await event.message.answer(f"Строки с ошибками: {lessons_result['error_rows'][:20]}")
    except Exception as e:
        logger.exception("Failed to reload lessons")
        await event.message.answer(f"\u274c Ошибка загрузки уроков: {_short_error(e)}")
        return

    try:
        links_result = await reload_lesson_links_data(session, content["links"])
        await event.message.answer(f"\u2705 Ссылки: {links_result['links']} загружено")
    except Exception as e:
        logger.exception("Failed to reload lesson links")
        await event.message.answer(f"\u274c Ошибка загрузки ссылок: {_short_error(e)}")
        return

    await event.message.answer("\u2705 Загрузка данных завершена!")


@router.message_created(Command("stats"))
async def cmd_stats(event: MessageCreated, session: AsyncSession):
    if not is_admin(event.message.sender.user_id):
        return
    user_count = await user_service.get_user_count(session)
    await event.message.answer(f"\U0001f4ca Статистика:\n\nПользователей: {user_count}")
