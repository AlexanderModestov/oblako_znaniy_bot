import asyncio
import logging

from aiogram.types import MenuButtonWebApp, WebAppInfo

from src.config import get_settings
from src.telegram.bot import create_bot, create_dispatcher
from src.telegram.handlers import register_all_routers
from src.telegram.middlewares import DatabaseMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    settings = get_settings()
    logger.info("Bot starting...")

    bot = create_bot()
    dp = create_dispatcher()

    dp.update.middleware(DatabaseMiddleware())
    register_all_routers(dp)

    if settings.web_app_url:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Регистрация",
                web_app=WebAppInfo(url=settings.web_app_url),
            )
        )
        logger.info("MenuButton set to Web App: %s", settings.web_app_url)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
