import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.config import get_settings
from src.core.services.loader import reload_lessons_data, reload_schools_data, reload_subjects_data
from src.core.services.user import UserService

router = Router()
logger = logging.getLogger(__name__)
user_service = UserService()


def is_admin(user_id: int) -> bool:
    return user_id in get_settings().admin_ids


@router.message(Command("reload"))
async def cmd_reload(message: Message, session):
    logger.info("Reload requested by user_id=%s, admin_ids=%s", message.from_user.id, get_settings().admin_ids)
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет прав для этой команды.")
        return

    await message.answer("\u23f3 Загрузка данных...")

    try:
        subjects_result = await reload_subjects_data(session)
        await message.answer(
            f"\u2705 Предметы: {subjects_result['subjects']} загружено"
        )
    except Exception as e:
        logger.exception("Failed to reload subjects")
        await message.answer(f"\u274c Ошибка загрузки предметов: {e}")

    try:
        schools_result = await reload_schools_data(session)
        await message.answer(
            f"\u2705 Регионы: {schools_result['regions']}, "
            f"Муниципалитеты: {schools_result['municipalities']}, "
            f"Школы: {schools_result['schools']}"
        )
    except Exception as e:
        logger.exception("Failed to reload schools")
        await message.answer(f"\u274c Ошибка загрузки школ: {e}")

    try:
        lessons_result = await reload_lessons_data(session)
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
        await message.answer(f"\u274c Ошибка загрузки уроков: {e}")


@router.message(Command("stats"))
async def cmd_stats(message: Message, session):
    if not is_admin(message.from_user.id):
        return

    user_count = await user_service.get_user_count(session)
    await message.answer(f"\U0001f4ca Статистика:\n\nПользователей: {user_count}")
