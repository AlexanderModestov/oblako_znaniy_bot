"""Research where a term appears across lesson columns.

For each term: counts matches in ``title``, ``section``, ``topic``,
``description`` (case-insensitive ILIKE), then prints up to 3 example rows
per column that has hits. Helps decide whether to expand ``search_vector``.

Usage:
    python -m scripts.research_term пушкин "петр 1" "великая отечественная"

With no args, runs the default query list used by ``soft_search_smoke``.
"""

import asyncio
import sys

from sqlalchemy import text

from src.core.database import get_async_session

DEFAULT_TERMS = [
    "пушкин",
    "петр",
    "ньютон",
    "егэ",
    "впр",
    "великая отечественная",
    "лабораторн",
]

COLUMNS = ("title", "section", "topic", "description")


async def research(term: str) -> None:
    like = f"%{term}%"
    sf = get_async_session()
    async with sf() as session:
        counts_sql = text(f"""
            SELECT
              COUNT(*) FILTER (WHERE title       ILIKE :p) AS title,
              COUNT(*) FILTER (WHERE section     ILIKE :p) AS section,
              COUNT(*) FILTER (WHERE topic       ILIKE :p) AS topic,
              COUNT(*) FILTER (WHERE description ILIKE :p) AS description
            FROM lessons
        """)
        row = (await session.execute(counts_sql, {"p": like})).one()
        counts = dict(row._mapping)

        print(f"\n══ {term!r}")
        print(f"  title={counts['title']}  section={counts['section']}  "
              f"topic={counts['topic']}  description={counts['description']}")

        for col in COLUMNS:
            if not counts[col]:
                continue
            ex_sql = text(f"""
                SELECT title, section, topic,
                       LEFT(description, 180) AS description
                FROM lessons
                WHERE {col} ILIKE :p
                LIMIT 3
            """)
            examples = (await session.execute(ex_sql, {"p": like})).all()
            print(f"  examples from {col}:")
            for ex in examples:
                m = ex._mapping
                print(f"    - title: {m['title']}")
                if col != "title":
                    print(f"      {col}: {m[col]}")


async def main(terms: list[str]) -> None:
    for t in terms:
        await research(t)


if __name__ == "__main__":
    args = sys.argv[1:] or DEFAULT_TERMS
    asyncio.run(main(args))
