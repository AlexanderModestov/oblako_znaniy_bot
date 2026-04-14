"""Lesson search service.

Level 1 (lexical) routes through ``fts_search_fuzzy`` when
``settings.enable_fuzzy_search`` is True: an OR-FTS with prefix matching
on ``search_vector`` unioned with a pg_trgm similarity fallback on
``title``, ranked on a single 0..1 score. When the flag is False, the
strict AND ``plainto_tsquery`` path (``fts_search``) is used — kept as a
rollback. Level 2 (lexical + semantic embeddings) is unaffected.

See ``docs/plans/2026-04-13-soft-search-design.md`` and
``docs/plans/2026-04-14-soft-search-implementation.md`` for rationale.
"""

import logging
import re

from openai import AsyncOpenAI
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.config import get_settings
from src.core.models import Lesson
from src.core.schemas import ClarifyOption, ClarifyResult, LessonResult, SearchResult

logger = logging.getLogger(__name__)

_ABBR_RE = re.compile(r"^[А-ЯЁA-Z]{2,5}$")

_TSQUERY_SPECIALS = re.compile(r"[&|!():*]")
_SPLIT_RE = re.compile(r"\s+")


def _normalize_tokens(query: str) -> list[str]:
    """Lowercase, strip tsquery specials, split into tokens,
    drop single-char non-digit tokens."""
    if not query:
        return []
    cleaned = _TSQUERY_SPECIALS.sub(" ", query.lower())
    raw = [t.strip(".,;:!?\"'()[]{}") for t in _SPLIT_RE.split(cleaned)]
    return [t for t in raw if t and (len(t) >= 2 or t.isdigit())]


def _build_or_tsquery_string(tokens: list[str]) -> str:
    """Build a tsquery OR-string. Word tokens get prefix matching ('закон:*');
    pure-digit tokens stay exact ('2') — otherwise '2:*' matches any number
    starting with 2 (2000, 2008, 2012, ...), flooding queries like
    '2 закон ньютона' with year-based history lessons."""
    parts = [t if t.isdigit() else f"{t}:*" for t in tokens]
    return " | ".join(parts)


def _build_tsquery(query: str):
    """AND logic: all words must be present. Uses plainto_tsquery for all cases."""
    return func.plainto_tsquery("russian", query)


def _abbr_filters(query: str):
    """Return SQLAlchemy conditions requiring each abbreviation to appear literally in title."""
    conditions = []
    for word in query.strip().split():
        if _ABBR_RE.match(word):
            conditions.append(Lesson.title.ilike(f"%{word}%"))
    return conditions


class SearchService:
    def __init__(self):
        settings = get_settings()
        self.fts_min_results = settings.fts_min_results
        self.similarity_threshold = settings.semantic_similarity_threshold
        self.per_page = settings.results_per_page
        self.clarify_threshold = settings.search_clarify_threshold
        self.trigram_threshold = settings.trigram_similarity_threshold
        self.trigram_title_w = settings.trigram_title_weight
        self.fts_floor = settings.fts_score_floor
        self.fuzzy_enabled = settings.enable_fuzzy_search

    async def fts_search(self, session: AsyncSession, query: str, page: int = 1) -> tuple[list[LessonResult], int]:
        ts_query = _build_tsquery(query)
        abbr_conds = _abbr_filters(query)

        count_q = select(func.count(Lesson.id)).where(Lesson.search_vector.op("@@")(ts_query))
        for cond in abbr_conds:
            count_q = count_q.where(cond)
        count_result = await session.execute(count_q)
        total = count_result.scalar() or 0

        offset = (page - 1) * self.per_page
        na_last = case((Lesson.url == "N/A", 1), else_=0)
        q = (
            select(Lesson)
            .options(joinedload(Lesson.subject))
            .where(Lesson.search_vector.op("@@")(ts_query))
            .order_by(na_last, func.ts_rank(Lesson.search_vector, ts_query).desc())
            .offset(offset).limit(self.per_page)
        )
        for cond in abbr_conds:
            q = q.where(cond)
        result = await session.execute(q)

        lessons = [
            LessonResult(
                title=l.title, url=l.url,
                description=l.description,
                subject=l.subject.name,
                grade=l.grade,
                section=l.section,
                topic=l.topic,
                is_semantic=False,
            )
            for l in result.scalars().unique().all()
        ]
        return lessons, total

    async def fts_search_fuzzy(
        self, session: AsyncSession, query: str, page: int = 1
    ) -> tuple[list[LessonResult], int]:
        """OR-FTS with prefix, unioned with pg_trgm fallback on title.
        Returns (page_results, total_count)."""
        from sqlalchemy import text

        tokens = _normalize_tokens(query)
        if not tokens:
            return [], 0

        ts_str = _build_or_tsquery_string(tokens)
        full_q = " ".join(tokens)
        thr = self.trigram_threshold
        floor = self.fts_floor
        title_w = self.trigram_title_w

        sql = text(f"""
            WITH fts AS (
                SELECT id,
                       {floor} + {1 - floor} * LEAST(ts_rank(search_vector, to_tsquery('russian', cast(:ts as text))), 1.0) AS score
                FROM lessons
                WHERE search_vector @@ to_tsquery('russian', cast(:ts as text))
            ),
            trg AS (
                SELECT id,
                       {title_w} * similarity(title, cast(:q as text)) AS score
                FROM lessons
                WHERE similarity(title, cast(:q as text)) > cast(:thr as float)
            ),
            merged AS (
                SELECT id, MAX(score) AS score FROM (
                    SELECT id, score FROM fts
                    UNION ALL
                    SELECT id, score FROM trg
                ) u
                GROUP BY id
            )
            SELECT m.id, m.score
            FROM merged m
            JOIN lessons l ON l.id = m.id
            ORDER BY (CASE WHEN l.url = 'N/A' THEN 1 ELSE 0 END),
                     m.score DESC,
                     m.id
        """)

        rows = (await session.execute(
            sql, {"ts": ts_str, "q": full_q, "thr": thr}
        )).all()

        total = len(rows)
        offset = (page - 1) * self.per_page
        page_ids = [r.id for r in rows[offset:offset + self.per_page]]
        if not page_ids:
            return [], total

        q = (
            select(Lesson)
            .options(joinedload(Lesson.subject))
            .where(Lesson.id.in_(page_ids))
        )
        result = await session.execute(q)
        by_id = {l.id: l for l in result.scalars().unique().all()}

        lessons = [
            LessonResult(
                title=by_id[i].title, url=by_id[i].url,
                description=by_id[i].description,
                subject=by_id[i].subject.name,
                grade=by_id[i].grade,
                section=by_id[i].section,
                topic=by_id[i].topic,
                is_semantic=False,
            )
            for i in page_ids if i in by_id
        ]
        return lessons, total

    async def semantic_search(self, session: AsyncSession, query: str, exclude_ids: list[int] | None = None, limit: int = 10) -> list[LessonResult]:
        try:
            settings = get_settings()
            client = AsyncOpenAI(api_key=settings.openai_api_key)
            response = await client.embeddings.create(model="text-embedding-3-small", input=query)
            query_embedding = response.data[0].embedding
        except Exception:
            logger.exception("Failed to generate query embedding")
            return []

        q = (
            select(Lesson, Lesson.embedding.cosine_distance(query_embedding).label("distance"))
            .options(joinedload(Lesson.subject))
            .where(Lesson.embedding.is_not(None))
        )
        if exclude_ids:
            q = q.where(Lesson.id.notin_(exclude_ids))
        q = q.order_by("distance").limit(limit)
        result = await session.execute(q)

        lessons = []
        for row in result.all():
            lesson = row[0]
            distance = row[1]
            similarity = 1 - distance
            if similarity >= self.similarity_threshold:
                lessons.append(
                    LessonResult(
                        title=lesson.title, url=lesson.url,
                        description=lesson.description,
                        subject=lesson.subject.name,
                        grade=lesson.grade,
                        section=lesson.section,
                        topic=lesson.topic,
                        is_semantic=True,
                    )
                )
        return lessons

    async def _build_level_results(self, session: AsyncSession, query: str, level: int) -> list[LessonResult]:
        """Build accumulated lesson list for level 2 (no pagination)."""
        and_lessons = await self.fts_search_all(session, query)

        and_id_query = select(Lesson.id).where(
            Lesson.search_vector.op("@@")(_build_tsquery(query))
        )
        and_id_result = await session.execute(and_id_query)
        and_ids = [row[0] for row in and_id_result.all()]

        semantic_lessons = await self.semantic_search(session, query, exclude_ids=and_ids)
        seen_urls = {l.url for l in and_lessons}
        combined = and_lessons + [l for l in semantic_lessons if l.url not in seen_urls]

        return combined

    async def search_by_level(self, session: AsyncSession, query: str, level: int, page: int = 1) -> SearchResult:
        """Search at the given level (1=AND, 2=AND+semantic), paginated."""
        if level not in (1, 2):
            raise ValueError(f"Invalid search level: {level!r}. Must be 1 or 2.")
        if level == 1:
            if self.fuzzy_enabled:
                lessons, total = await self.fts_search_fuzzy(session, query, page=page)
            else:
                lessons, total = await self.fts_search(session, query, page=page)
            return SearchResult(query=query, lessons=lessons, total=total, page=page, per_page=self.per_page)

        combined = await self._build_level_results(session, query, level)
        total = len(combined)
        offset = (page - 1) * self.per_page
        return SearchResult(
            query=query,
            lessons=combined[offset: offset + self.per_page],
            total=total,
            page=page,
            per_page=self.per_page,
        )

    async def get_all_lessons_for_level(self, session: AsyncSession, query: str, level: int) -> list[LessonResult]:
        """Get all lessons for a level without pagination — for clarification analysis."""
        if level == 1:
            if self.fuzzy_enabled:
                return await self.fts_search_all_fuzzy(session, query)
            return await self.fts_search_all(session, query)
        return await self._build_level_results(session, query, level)

    def check_clarification(
        self,
        lessons: list[LessonResult],
    ) -> ClarifyResult | None:
        """Analyze results and return adaptive clarification if needed.

        Priority: subjects → grades → topics.
        Returns None if below threshold or results are homogeneous.
        """
        if len(lessons) <= self.clarify_threshold:
            return None

        for level, field, fmt in [
            ("subject", "subject", lambda v, c: f"{v} ({c})"),
            ("grade", "grade", lambda v, c: f"{v} класс ({c})"),
            ("topic", "topic", lambda v, c: f"{v} ({c})"),
        ]:
            counts: dict[str, int] = {}
            for lesson in lessons:
                value = getattr(lesson, field)
                if value is None:
                    continue
                key = str(value)
                counts[key] = counts.get(key, 0) + 1

            if len(counts) <= 1:
                continue

            sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:7]
            options = [
                ClarifyOption(value=val, display=fmt(val, cnt), count=cnt)
                for val, cnt in sorted_items
            ]

            total = len(lessons)
            if level == "subject":
                message = f"Найдено {total} результатов. Выберите предмет:"
            elif level == "grade":
                subj = lessons[0].subject or ""
                message = f"Найдено {total} результатов по {subj}. Выберите класс:"
            else:
                subj = lessons[0].subject or ""
                grade = lessons[0].grade
                grade_str = f", {grade} класс" if grade else ""
                message = f"Найдено {total} результатов — {subj}{grade_str}. Выберите тему:"

            return ClarifyResult(level=level, options=options, message=message, total=total)

        return None

    async def fts_search_all_fuzzy(
        self, session: AsyncSession, query: str
    ) -> list[LessonResult]:
        """Same as fts_search_fuzzy but returns all hits (no pagination)."""
        all_lessons: list[LessonResult] = []
        page = 1
        while True:
            batch, total = await self.fts_search_fuzzy(session, query, page=page)
            if not batch:
                break
            all_lessons.extend(batch)
            if len(all_lessons) >= total:
                break
            page += 1
        return all_lessons

    async def fts_search_all(self, session: AsyncSession, query: str) -> list[LessonResult]:
        """Fetch all FTS results without pagination (for clarification analysis)."""
        ts_query = _build_tsquery(query)
        abbr_conds = _abbr_filters(query)
        na_last = case((Lesson.url == "N/A", 1), else_=0)
        q = (
            select(Lesson)
            .options(joinedload(Lesson.subject))
            .where(Lesson.search_vector.op("@@")(ts_query))
            .order_by(na_last, func.ts_rank(Lesson.search_vector, ts_query).desc())
        )
        for cond in abbr_conds:
            q = q.where(cond)
        result = await session.execute(q)
        return [
            LessonResult(
                title=l.title, url=l.url,
                description=l.description,
                subject=l.subject.name,
                grade=l.grade,
                section=l.section,
                topic=l.topic,
                is_semantic=False,
            )
            for l in result.scalars().unique().all()
        ]
