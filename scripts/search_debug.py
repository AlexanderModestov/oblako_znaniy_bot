"""Ad-hoc debug of why queries return what they return.

For each of 3 showcase queries, inspects:
  - what lessons exist containing the key term anywhere (title/section/topic/description)
  - what the fuzzy SQL actually returns with per-row score + coverage
  - which columns contribute to search_vector match

Usage:
    python -m scripts.search_debug
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from src.core.database import get_async_session
from src.core.services.search import _normalize_tokens, _build_or_tsquery_string


CASES = [
    ("пушкин", ["пушкин", "пушкина"]),
    ("лабораторные по физике", ["лаборатор", "физик"]),
    ("2 закон ньютона", ["ньютон", "закон"]),
]


async def show_case(query: str, ilike_terms: list[str]) -> None:
    print(f"\n{'=' * 80}\nQUERY: {query!r}\n{'=' * 80}")
    tokens = _normalize_tokens(query)
    ts_str = _build_or_tsquery_string(tokens)
    print(f"tokens={tokens}")
    print(f"tsquery OR = {ts_str!r}")

    sf = get_async_session()
    async with sf() as session:
        # 1. How many lessons contain each term anywhere (title | section | topic | description)?
        print("\n-- corpus coverage per term --")
        for term in ilike_terms:
            like = f"%{term}%"
            sql = text(
                """
                SELECT
                  SUM(CASE WHEN title ILIKE :t THEN 1 ELSE 0 END) AS in_title,
                  SUM(CASE WHEN section ILIKE :t THEN 1 ELSE 0 END) AS in_section,
                  SUM(CASE WHEN topic ILIKE :t THEN 1 ELSE 0 END) AS in_topic,
                  SUM(CASE WHEN description ILIKE :t THEN 1 ELSE 0 END) AS in_desc,
                  COUNT(*) FILTER (WHERE
                      title ILIKE :t OR section ILIKE :t
                      OR topic ILIKE :t OR description ILIKE :t) AS any_col
                FROM lessons
                """
            )
            row = (await session.execute(sql, {"t": like})).one()
            print(
                f"  '{term}': title={row.in_title}, section={row.in_section}, "
                f"topic={row.in_topic}, desc={row.in_desc}, ANY={row.any_col}"
            )

        # 2. Top 15 lessons matching tsquery OR (the fuzzy FTS leg), with per-token coverage.
        print("\n-- top 15 FTS (OR-tsquery) rows by ts_rank --")
        params: dict = {"ts": ts_str}
        # rank by raw ts_rank desc
        sql = text(
            """
            SELECT id, title, section, topic,
                   ts_rank(search_vector, to_tsquery('russian', cast(:ts as text))) AS rank
            FROM lessons
            WHERE search_vector @@ to_tsquery('russian', cast(:ts as text))
            ORDER BY rank DESC
            LIMIT 15
            """
        )
        rows = (await session.execute(sql, params)).all()
        for r in rows:
            print(f"  rank={r.rank:.4f}  [{r.id}] {r.title}")
            if r.section or r.topic:
                print(f"        section={r.section!r}  topic={r.topic!r}")

        # 3. Top 10 trigram candidates on title only.
        print("\n-- top 10 title trigram matches --")
        sql = text(
            """
            SELECT id, title, similarity(title, cast(:q as text)) AS sim
            FROM lessons
            WHERE similarity(title, cast(:q as text)) > 0.1
            ORDER BY sim DESC
            LIMIT 10
            """
        )
        rows = (await session.execute(sql, {"q": query})).all()
        for r in rows:
            print(f"  sim={r.sim:.3f}  [{r.id}] {r.title}")


async def main() -> None:
    for q, terms in CASES:
        await show_case(q, terms)


if __name__ == "__main__":
    asyncio.run(main())
