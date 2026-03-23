from maxapi import Dispatcher

from src.max.handlers.admin import router as admin_router
from src.max.handlers.menu import router as menu_router
from src.max.handlers.param_search import router as param_search_router
from src.max.handlers.search import router as search_router
from src.max.handlers.start import router as start_router


def register_all_routers(dp: Dispatcher) -> None:
    dp.include_routers(start_router)
    dp.include_routers(admin_router)
    dp.include_routers(menu_router)
    dp.include_routers(param_search_router)
    dp.include_routers(search_router)  # catch-all — must be last
