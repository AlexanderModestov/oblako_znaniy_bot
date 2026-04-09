import logging
import re

from openai import AsyncOpenAI
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.config import get_settings
from src.core.models import Lesson
from src.core.schemas import ClarifyOption, ClarifyResult, LessonResult, SearchResult

logger = logging.getLogger(__name__)

_ABBR_RE = re.compile(r"^[А-ЯЁA-Z]{2,5}$")


def _build_tsquery(query: str):
    """AND logic: all words must be present. Uses plainto_tsquery for all cases."""
    return func.plainto_tsquery("russian", query)


def _build_tsquery_or(query: str):
    """OR logic: any word matches. Used as fallback when AND yields too few results."""
    words = query.strip().split()
    if len(words) <= 1:
        return func.plainto_tsquery("russian", query)
    return func.websearch_to_tsquery("russian", " OR ".join(words))


def _abbr_filters(query: str):
    """Return SQLAlchemy conditions requiring each abbreviation to appear literally."""
    conditions = []
    for word in query.strip().split():
        if _ABBR_RE.match(word):
            pat = f"%{word}%"
            conditions.append(or_(
                Lesson.title.ilike(pat),
                Lesson.description.ilike(pat),
                Lesson.section.ilike(pat),
                Lesson.topic.ilike(pat),
            ))
    return conditions


class SearchService:
    def __init__(self):
        settings = get_settings()
        self.fts_min_results = settings.fts_min_results
        self.similarity_threshold = settings.semantic_similarity_threshold
        self.per_page = settings.results_per_page
        self.clarify_threshold = settings.search_clarify_threshold

    async def fts_search(self, session: AsyncSession, query: str, page: int = 1, use_or: bool = False) -> tuple[list[LessonResult], int]:
        ts_query = _build_tsquery_or(query) if use_or else _build_tsquery(query)
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
        """Build accumulated lesson list for level 2 or 3 (no pagination)."""
        and_lessons = await self.fts_search_all(session, query)

        and_id_query = select(Lesson.id).where(
            Lesson.search_vector.op("@@")(_build_tsquery(query))
        )
        and_id_result = await session.execute(and_id_query)
        and_ids = [row[0] for row in and_id_result.all()]

        semantic_lessons = await self.semantic_search(session, query, exclude_ids=and_ids)
        seen_urls = {l.url for l in and_lessons}
        combined = and_lessons + [l for l in semantic_lessons if l.url not in seen_urls]

        if level >= 3:
            seen_urls = {l.url for l in combined}
            or_lessons = await self.fts_search_all(session, query, use_or=True)
            combined += [l for l in or_lessons if l.url not in seen_urls]

        return combined

    async def search_by_level(self, session: AsyncSession, query: str, level: int, page: int = 1) -> SearchResult:
        """Search at the given level (1=AND, 2=AND+semantic, 3=AND+semantic+OR), paginated."""
        if level not in (1, 2, 3):
            raise ValueError(f"Invalid search level: {level!r}. Must be 1, 2, or 3.")
        if level == 1:
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

    async def fts_search_all(self, session: AsyncSession, query: str, use_or: bool = False) -> list[LessonResult]:
        """Fetch all FTS results without pagination (for clarification analysis)."""
        ts_query = _build_tsquery_or(query) if use_or else _build_tsquery(query)
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
