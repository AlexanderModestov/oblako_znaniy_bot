from typing import Any, Awaitable, Callable

from maxapi.filters.middleware import BaseMiddleware
from maxapi.types import UpdateUnion

from src.core.database import get_async_session


class DatabaseMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event_object: UpdateUnion,
        data: dict[str, Any],
    ) -> Any:
        session_factory = get_async_session()
        async with session_factory() as session:
            data["session"] = session
            return await handler(event_object, data)
