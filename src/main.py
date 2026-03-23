import asyncio
import logging


from src.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def start_telegram():
    from src.telegram.bot import create_bot, create_dispatcher
    from src.telegram.handlers import register_all_routers
    from src.telegram.middlewares import DatabaseMiddleware

    settings = get_settings()
    bot = create_bot()
    dp = create_dispatcher()
    dp.update.middleware(DatabaseMiddleware())
    register_all_routers(dp)


    logger.info("Telegram bot starting polling...")
    await dp.start_polling(bot)


async def start_max():
    from src.max.bot import create_max_bot, create_max_dispatcher
    from src.max.handlers import register_all_routers
    from src.max.middlewares import DatabaseMiddleware

    bot = create_max_bot()
    dp = create_max_dispatcher()
    dp.middleware(DatabaseMiddleware())
    register_all_routers(dp)

    logger.info("MAX bot starting polling...")
    await dp.start_polling(bot)


async def main():
    settings = get_settings()
    tasks = []

    if settings.enable_telegram:
        tasks.append(start_telegram())
        logger.info("Telegram bot enabled")
    else:
        logger.info("Telegram bot disabled")

    if settings.enable_max:
        if not settings.max_bot_token:
            logger.warning("MAX bot enabled but MAX_BOT_TOKEN not set, skipping")
        else:
            tasks.append(start_max())
            logger.info("MAX bot enabled")
    else:
        logger.info("MAX bot disabled")

    if not tasks:
        logger.error("No bots enabled, exiting")
        return

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
