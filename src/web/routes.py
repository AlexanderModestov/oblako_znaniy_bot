import logging

from aiogram import Bot
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.core.database import get_async_session
from src.core.schemas import UserCreate
from src.core.services.user import UserService
from src.telegram.keyboards import search_choice_keyboard
from src.web.auth import get_platform_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")
user_service = UserService()


async def get_session():
    session_factory = get_async_session()
    async with session_factory() as session:
        yield session


@router.post("/auth")
async def auth(
    user: dict = Depends(get_platform_user),
    session: AsyncSession = Depends(get_session),
):
    platform = user.get("platform", "telegram")
    user_id = user["id"]

    if platform == "max":
        db_user = await user_service.get_by_max_user_id(session, user_id)
    else:
        db_user = await user_service.get_by_telegram_id(session, user_id)

    return {
        "user_id": user_id,
        "platform": platform,
        "status": "existing" if db_user else "new",
        "full_name": db_user.full_name if db_user else None,
    }


@router.get("/regions")
async def regions(
    q: str = Query(default="", max_length=100),
    user: dict = Depends(get_platform_user),
    session: AsyncSession = Depends(get_session),
):
    if q:
        return await user_service.search_regions(session, q, limit=50)
    return await user_service.get_all_regions(session)


@router.get("/municipalities/{region_id}")
async def municipalities(
    region_id: int,
    user: dict = Depends(get_platform_user),
    session: AsyncSession = Depends(get_session),
):
    return await user_service.get_municipalities_by_region(session, region_id)


@router.get("/schools/{region_id}")
async def schools(
    region_id: int,
    q: str = Query(default="", max_length=100),
    municipality: str = Query(default="", max_length=255),
    user: dict = Depends(get_platform_user),
    session: AsyncSession = Depends(get_session),
):
    if q:
        return await user_service.search_schools(session, region_id, q, limit=50)
    if municipality:
        return await user_service.get_schools_by_municipality(session, region_id, municipality)
    return await user_service.get_schools_by_region(session, region_id)


@router.get("/subjects")
async def subjects(
    user: dict = Depends(get_platform_user),
    session: AsyncSession = Depends(get_session),
):
    return await user_service.get_all_subjects(session)


@router.post("/register")
async def register(
    data: UserCreate,
    user: dict = Depends(get_platform_user),
    session: AsyncSession = Depends(get_session),
    bot_msg_id: int | None = Query(default=None),
):
    platform = user.get("platform", "telegram")
    if platform == "max":
        data.max_user_id = user["id"]
        data.telegram_id = None
    else:
        data.telegram_id = user["id"]
        data.max_user_id = None
    db_user = await user_service.create_user(session, data)

    if platform == "telegram" and data.telegram_id:
        try:
            bot = Bot(token=get_settings().bot_token)
            text = (
                f"Регистрация завершена, {data.full_name}!\n\n"
                "Выберите способ поиска:"
            )
            kb = search_choice_keyboard()
            async with bot:
                if bot_msg_id:
                    await bot.edit_message_text(
                        chat_id=data.telegram_id,
                        message_id=bot_msg_id,
                        text=text,
                        reply_markup=kb,
                    )
                else:
                    await bot.send_message(
                        chat_id=data.telegram_id, text=text, reply_markup=kb
                    )
        except Exception:
            logger.exception("Failed to send post-registration message")

    return {"ok": True, "user_id": db_user.id}
