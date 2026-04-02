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
from src.telegram.keyboards import broadcast_consent_keyboard

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
            f"Школы: {schools_result['schools']}\n"
            f"Строк: {schools_result['rows_total']}, "
            f"с муниципалитетом: {schools_result['has_municipality']}"
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


@router.message(Command("reload_schools"))
async def cmd_reload_schools(message: Message, session):
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет прав для этой команды.")
        return

    await message.answer("\u23f3 Загрузка школ...")
    try:
        schools_result = await reload_schools_data(session)
        await message.answer(
            f"\u2705 Регионы: {schools_result['regions']}, "
            f"Школы: {schools_result['schools']}\n"
            f"Строк: {schools_result['rows_total']}, "
            f"с муниципалитетом: {schools_result['has_municipality']}"
        )
    except Exception as e:
        logger.exception("Failed to reload schools")
        await message.answer(f"\u274c Ошибка загрузки школ: {_short_error(e)}")
        return

    await message.answer("\u2705 Загрузка школ завершена!")


@router.message(Command("reload_lessons"))
async def cmd_reload_lessons(message: Message, session):
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет прав для этой команды.")
        return

    await message.answer("\u23f3 Загрузка контента из Google Sheets...")
    try:
        content = fetch_all_content_from_sheets()
    except Exception as e:
        logger.exception("Failed to fetch content from sheets")
        await message.answer(f"\u274c Ошибка загрузки из Google Sheets: {_short_error(e)}")
        return

    try:
        subjects_result = await reload_subjects_data(session, content["subjects"])
        await message.answer(
            f"\u2705 Предметы: {subjects_result['subjects']} загружено"
        )
    except Exception as e:
        logger.exception("Failed to reload subjects")
        await message.answer(f"\u274c Ошибка загрузки предметов: {_short_error(e)}")
        return

    try:
        courses_result = await reload_courses_data(session, content["courses"])
        await message.answer(
            f"\u2705 Курсы: {courses_result['courses']} загружено"
        )
    except Exception as e:
        logger.exception("Failed to reload courses")
        await message.answer(f"\u274c Ошибка загрузки курсов: {_short_error(e)}")
        return

    try:
        sections_result = await reload_sections_data(session, content["sections"])
        await message.answer(
            f"\u2705 Разделы: {sections_result['sections']} загружено"
        )
    except Exception as e:
        logger.exception("Failed to reload sections")
        await message.answer(f"\u274c Ошибка загрузки разделов: {_short_error(e)}")
        return

    try:
        topics_result = await reload_topics_data(session, content["topics"])
        await message.answer(
            f"\u2705 Темы: {topics_result['topics']} загружено"
        )
    except Exception as e:
        logger.exception("Failed to reload topics")
        await message.answer(f"\u274c Ошибка загрузки тем: {_short_error(e)}")
        return

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

    try:
        links_result = await reload_lesson_links_data(session, content["links"])
        await message.answer(
            f"\u2705 Ссылки: {links_result['links']} загружено"
        )
    except Exception as e:
        logger.exception("Failed to reload lesson links")
        await message.answer(f"\u274c Ошибка загрузки ссылок: {_short_error(e)}")
        return

    await message.answer("\u2705 Загрузка контента завершена!")


def _broadcast_consent_text(html: bool = False) -> str:
    """Build broadcast consent text. html=True for Telegram (clickable link), False for MAX (plain URL)."""
    settings = get_settings()
    privacy_url = f"{settings.web_app_url}/privacy.html" if settings.web_app_url else ""
    link_text = "согласие на обработку персональных данных"
    if html and privacy_url:
        link = f'<a href="{privacy_url}">{link_text}</a>'
    elif privacy_url:
        link = f"{link_text} ({privacy_url})"
    else:
        link = link_text
    return (
        f"Мы обновили условия использования сервиса.\n\n"
        f"Для продолжения работы вам необходимо принять {link}, "
        f"которые вы оставили при регистрации на старте.\n\n"
        f"Пока согласие не принято, функция поиска будет приостановлена."
    )


def _create_max_bot():
    """Create Max bot instance for broadcast. Returns None if Max is not configured."""
    settings = get_settings()
    if not settings.enable_max or not settings.max_bot_token:
        return None
    from maxapi import Bot as MaxBot
    return MaxBot(token=settings.max_bot_token)


async def _send_to_max_user(max_bot, user, max_kb):
    """Send broadcast consent message to a Max user."""
    await max_bot.send_message(
        user_id=user.max_user_id,
        text=_broadcast_consent_text(html=False),
        attachments=[max_kb.as_markup()],
        disable_link_preview=True,
    )


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, session):
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет прав для этой команды.")
        return

    max_bot = _create_max_bot()

    args = message.text.split(maxsplit=1)
    # /broadcast <id> — send to specific user
    if len(args) > 1:
        try:
            target_user_id = int(args[1].strip())
        except ValueError:
            await message.answer("Неверный формат. Используйте: /broadcast <id>")
            return

        user = await user_service.get_by_id(session, target_user_id)
        if not user:
            await message.answer(f"Пользователь с id={target_user_id} не найден.")
            return
        if user.consent_given:
            await message.answer(f"Пользователь {user.full_name} (id={user.id}) уже дал согласие.")
            return
        if not user.telegram_id and not user.max_user_id:
            await message.answer(f"У пользователя {user.full_name} (id={user.id}) нет ни telegram_id, ни max_user_id.")
            return

        results = []
        if user.telegram_id:
            try:
                await message.bot.send_message(
                    user.telegram_id,
                    _broadcast_consent_text(html=True),
                    parse_mode="HTML",
                    reply_markup=broadcast_consent_keyboard(),
                )
                results.append("Telegram: OK")
            except Exception as e:
                results.append(f"Telegram: {_short_error(e)}")
        if user.max_user_id and max_bot:
            try:
                from src.max.keyboards import broadcast_consent_keyboard as max_broadcast_kb
                await _send_to_max_user(max_bot, user, max_broadcast_kb())
                results.append("Max: OK")
            except Exception as e:
                results.append(f"Max: {_short_error(e)}")

        await message.answer(
            f"Пользователь {user.full_name} (id={user.id}):\n" + "\n".join(results)
        )
        return

    # /broadcast — send to all users without consent
    tg_users = await user_service.get_users_without_consent(session, platform="telegram")
    max_users = await user_service.get_users_without_consent(session, platform="max") if max_bot else []

    if not tg_users and not max_users:
        await message.answer("Все пользователи уже дали согласие.")
        return

    total = len(tg_users) + len(max_users)
    await message.answer(f"\u23f3 Рассылка {total} пользователям (Telegram: {len(tg_users)}, Max: {len(max_users)})...")

    sent = 0
    failed = 0

    for user in tg_users:
        try:
            await message.bot.send_message(
                user.telegram_id,
                _broadcast_consent_text(html=True),
                parse_mode="HTML",
                reply_markup=broadcast_consent_keyboard(),
            )
            sent += 1
        except Exception as e:
            failed += 1
            logger.warning("Failed to send broadcast to user %s (telegram_id=%s): %s", user.id, user.telegram_id, e)

    if max_users and max_bot:
        from src.max.keyboards import broadcast_consent_keyboard as max_broadcast_kb
        max_kb = max_broadcast_kb()
        for user in max_users:
            try:
                await _send_to_max_user(max_bot, user, max_kb)
                sent += 1
            except Exception as e:
                failed += 1
                logger.warning("Failed to send broadcast to user %s (max_user_id=%s): %s", user.id, user.max_user_id, e)

    await message.answer(f"\u2705 Рассылка завершена.\nОтправлено: {sent}\nОшибок: {failed}")


@router.message(Command("stats"))
async def cmd_stats(message: Message, session):
    if not is_admin(message.from_user.id):
        return

    user_count = await user_service.get_user_count(session)
    await message.answer(f"\U0001f4ca Статистика:\n\nПользователей: {user_count}")
