import asyncio
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

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

router = Router()
logger = logging.getLogger(__name__)
user_service = UserService()


def is_admin(user_id: int) -> bool:
    return user_id in get_settings().admin_ids


def _short_error(e: Exception) -> str:
    return str(e)[:200]


@router.message(Command("reload"))
async def cmd_reload(message: Message, session):
    logger.info("Reload requested by user_id=%s, admin_ids=%s", message.from_user.id, get_settings().admin_ids)
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет прав для этой команды.")
        return

    await message.answer("\u23f3 Загрузка данных...")

    # 1. Schools (fetch + load)
    try:
        schools_result = await reload_schools_data(session)
        await message.answer(
            f"\u2705 Регионы: {schools_result['regions']}, "
            f"Школы: {schools_result['schools']}"
        )
    except Exception as e:
        logger.exception("Failed to reload schools")
        await message.answer(f"\u274c Ошибка загрузки школ: {_short_error(e)}")
        return

    # 2. Fetch all content tabs at once — pause to avoid rate limiting
    try:
        await message.answer("\u23f3 Ожидание перед загрузкой контента (квота API)...")
        await asyncio.sleep(60)
        await message.answer("\u23f3 Загрузка контента из Google Sheets...")
        content = fetch_all_content_from_sheets()
    except Exception as e:
        logger.exception("Failed to fetch content from sheets")
        await message.answer(f"\u274c Ошибка загрузки из Google Sheets: {_short_error(e)}")
        return

    # 3. Subjects
    try:
        subjects_result = await reload_subjects_data(session, content["subjects"])
        await message.answer(
            f"\u2705 Предметы: {subjects_result['subjects']} загружено"
        )
    except Exception as e:
        logger.exception("Failed to reload subjects")
        await message.answer(f"\u274c Ошибка загрузки предметов: {_short_error(e)}")
        return

    # 4. Courses
    try:
        courses_result = await reload_courses_data(session, content["courses"])
        await message.answer(
            f"\u2705 Курсы: {courses_result['courses']} загружено"
        )
    except Exception as e:
        logger.exception("Failed to reload courses")
        await message.answer(f"\u274c Ошибка загрузки курсов: {_short_error(e)}")
        return

    # 5. Sections
    try:
        sections_result = await reload_sections_data(session, content["sections"])
        await message.answer(
            f"\u2705 Разделы: {sections_result['sections']} загружено"
        )
    except Exception as e:
        logger.exception("Failed to reload sections")
        await message.answer(f"\u274c Ошибка загрузки разделов: {_short_error(e)}")
        return

    # 6. Topics
    try:
        topics_result = await reload_topics_data(session, content["topics"])
        await message.answer(
            f"\u2705 Темы: {topics_result['topics']} загружено"
        )
    except Exception as e:
        logger.exception("Failed to reload topics")
        await message.answer(f"\u274c Ошибка загрузки тем: {_short_error(e)}")
        return

    # 7. Lessons
    try:
        lessons_result = await reload_lessons_data(session, content["lessons"])
        emb_status = "\u2705" if lessons_result["embeddings"] else "\u26a0\ufe0f без эмбеддингов"
        await message.answer(
            f"\u2705 Уроки: {lessons_result['loaded']} загружено, "
            f"{lessons_result['errors']} ошибок\n"
            f"Эмбеддинги: {emb_status}"
        )
        if lessons_result["error_rows"]:
            await message.answer(f"Строки с ошибками: {lessons_result['error_rows'][:20]}")
    except Exception as e:
        logger.exception("Failed to reload lessons")
        await message.answer(f"\u274c Ошибка загрузки уроков: {_short_error(e)}")
        return

    # 8. Lesson links
    try:
        links_result = await reload_lesson_links_data(session, content["links"])
        await message.answer(
            f"\u2705 Ссылки: {links_result['links']} загружено"
        )
    except Exception as e:
        logger.exception("Failed to reload lesson links")
        await message.answer(f"\u274c Ошибка загрузки ссылок: {_short_error(e)}")
        return

    await message.answer("\u2705 Загрузка данных завершена!")


@router.message(Command("stats"))
async def cmd_stats(message: Message, session):
    if not is_admin(message.from_user.id):
        return

    user_count = await user_service.get_user_count(session)
    await message.answer(f"\U0001f4ca Статистика:\n\nПользователей: {user_count}")
