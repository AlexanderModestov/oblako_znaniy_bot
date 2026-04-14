"""Baseline measurement for soft-search quality and latency.

Runs the fixed golden-set queries through both Level 1 (lexical, fuzzy path
when enabled) and Level 2 (lexical + semantic) against the configured DB.
Measures latency (3 runs, reports median) and prints top-5 results per query.
Writes a markdown report to ``tasks/soft-search-baseline.md``.

Usage:
    python -m scripts.search_baseline
"""

from __future__ import annotations

import asyncio
import statistics
import time
from pathlib import Path

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

RUNS = 3
TOP_N = 5
OUTPUT = Path("tasks/soft-search-baseline.md")


async def time_query(service: SearchService, query: str, level: int):
    sf = get_async_session()
    timings_ms: list[float] = []
    last_result = None
    for _ in range(RUNS):
        async with sf() as session:
            t0 = time.perf_counter()
            result = await service.search_by_level(session, query, level=level, page=1)
            timings_ms.append((time.perf_counter() - t0) * 1000)
            last_result = result
    return last_result, statistics.median(timings_ms), min(timings_ms), max(timings_ms)


def fmt_lesson(i: int, l) -> str:
    grade = f" / {l.grade} кл" if l.grade else ""
    tag = " [sem]" if getattr(l, "is_semantic", False) else ""
    return f"  {i}. [{l.subject}{grade}]{tag} {l.title}"


async def main() -> None:
    settings = get_settings()
    service = SearchService()

    lines: list[str] = []
    header = [
        "# Soft-search baseline",
        "",
        f"- `enable_fuzzy_search = {settings.enable_fuzzy_search}`",
        f"- `trigram_similarity_threshold = {settings.trigram_similarity_threshold}`",
        f"- `trigram_title_weight = {settings.trigram_title_weight}`",
        f"- `fts_score_floor = {settings.fts_score_floor}`",
        f"- `fts_min_results = {settings.fts_min_results}`",
        f"- `semantic_similarity_threshold = {settings.semantic_similarity_threshold}`",
        f"- runs per (query, level): {RUNS}, top-N shown: {TOP_N}",
        "",
        "| Query | L1 total | L1 median ms | L2 total | L2 median ms |",
        "|---|---:|---:|---:|---:|",
    ]
    lines.extend(header)

    detail: list[str] = []

    for q in QUERIES:
        print(f"\n=== {q!r}")
        r1, m1, mn1, mx1 = await time_query(service, q, level=1)
        r2, m2, mn2, mx2 = await time_query(service, q, level=2)
        print(f"  L1 total={r1.total}  median={m1:.0f}ms (min {mn1:.0f} / max {mx1:.0f})")
        print(f"  L2 total={r2.total}  median={m2:.0f}ms (min {mn2:.0f} / max {mx2:.0f})")

        lines.append(
            f"| `{q}` | {r1.total} | {m1:.0f} | {r2.total} | {m2:.0f} |"
        )

        detail.append(f"\n### `{q}`\n")
        detail.append(
            f"L1: total={r1.total}, median={m1:.0f}ms (min {mn1:.0f} / max {mx1:.0f})"
        )
        detail.append("")
        if r1.lessons:
            for i, l in enumerate(r1.lessons[:TOP_N], 1):
                detail.append(fmt_lesson(i, l))
                print(fmt_lesson(i, l))
        else:
            detail.append("  (no results)")

        detail.append("")
        detail.append(
            f"L2: total={r2.total}, median={m2:.0f}ms (min {mn2:.0f} / max {mx2:.0f})"
        )
        detail.append("")
        if r2.lessons:
            for i, l in enumerate(r2.lessons[:TOP_N], 1):
                detail.append(fmt_lesson(i, l))
        else:
            detail.append("  (no results)")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines + ["", "## Top results per query", *detail]) + "\n", encoding="utf-8")
    print(f"\nReport written to {OUTPUT}")


if __name__ == "__main__":
    asyncio.run(main())
