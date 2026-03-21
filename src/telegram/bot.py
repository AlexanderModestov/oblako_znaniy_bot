from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from src.config import get_settings


def create_bot() -> Bot:
    return Bot(token=get_settings().bot_token)


def create_dispatcher() -> Dispatcher:
    return Dispatcher(storage=MemoryStorage())
