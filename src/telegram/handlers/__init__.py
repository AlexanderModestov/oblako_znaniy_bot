from aiogram import Router

from src.telegram.handlers.admin import router as admin_router
from src.telegram.handlers.menu import router as menu_router
from src.telegram.handlers.param_search import router as param_search_router
from src.telegram.handlers.search import router as search_router
from src.telegram.handlers.start import router as start_router


def register_all_routers(parent_router: Router) -> None:
    parent_router.include_router(start_router)
    parent_router.include_router(admin_router)
    parent_router.include_router(menu_router)
    parent_router.include_router(param_search_router)
    parent_router.include_router(search_router)  # catch-all — must be last
