import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    from src.config import get_settings
    settings = get_settings()
    logger.info("Bot starting...")
    logger.info("Admin IDs: %s", settings.admin_ids)


if __name__ == "__main__":
    asyncio.run(main())
