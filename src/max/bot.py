from maxapi import Bot, Dispatcher

from src.config import get_settings


def create_max_bot() -> Bot:
    return Bot(token=get_settings().max_bot_token)


def create_max_dispatcher() -> Dispatcher:
    return Dispatcher()
