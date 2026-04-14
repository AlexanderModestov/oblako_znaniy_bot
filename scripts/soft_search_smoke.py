"""Manual smoke test for soft-search level 1.

Runs a fixed list of queries through ``SearchService.search_by_level(level=1)``
against the configured dev database and prints top-5 per query with both the
fuzzy path (``ENABLE_FUZZY_SEARCH=true``) and the strict path (flag off).

Usage:
    python -m scripts.soft_search_smoke

Requires a working ``DATABASE_URL`` and that migration 012 has been applied.
"""

import asyncio

from src.config import get_settings
from src.core.database import get_async_session
from src.core.services.search import SearchService

QUERIES = [
    "пушкин",
    "петр 1",
    "2 закон ньютона",
    "подготовка к ЕГЭ по физике",
    "впр по химии",
    "великая отечественная война",
    "лабораторные по физике",
    "лабораторные",
    "лабораторные работы",
]


async def run_query(service: SearchService, query: str) -> None:
    sf = get_async_session()
    async with sf() as session:
        result = await service.search_by_level(session, query, level=1, page=1)
    print(f"\n── {query!r}  (total={result.total})")
    if not result.lessons:
        print("    (no results)")
        return
    for i, l in enumerate(result.lessons, 1):
        grade = f" / {l.grade} кл" if l.grade else ""
        print(f"    {i}. [{l.subject}{grade}] {l.title}")


async def main() -> None:
    settings = get_settings()
    print(f"enable_fuzzy_search = {settings.enable_fuzzy_search}")
    service = SearchService()
    for q in QUERIES:
        await run_query(service, q)


if __name__ == "__main__":
    asyncio.run(main())
