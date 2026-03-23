import logging

from openai import AsyncOpenAI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.config import get_settings
from src.core.models import Lesson
from src.core.schemas import LessonResult, SearchResult

logger = logging.getLogger(__name__)


def _build_tsquery(query: str):
    """Build a tsquery expression: single word uses plainto_tsquery, multiple words use OR logic."""
    words = query.strip().split()
    if len(words) <= 1:
        return func.plainto_tsquery("russian", query)
    return func.websearch_to_tsquery("russian", " OR ".join(words))


class SearchService:
    def __init__(self):
        settings = get_settings()
        self.fts_min_results = settings.fts_min_results
        self.similarity_threshold = settings.semantic_similarity_threshold
        self.per_page = settings.results_per_page

    async def fts_search(self, session: AsyncSession, query: str, page: int = 1) -> tuple[list[LessonResult], int]:
        ts_query = _build_tsquery(query)

        count_q = select(func.count(Lesson.id)).where(Lesson.search_vector.op("@@")(ts_query))
        count_result = await session.execute(count_q)
        total = count_result.scalar() or 0

        offset = (page - 1) * self.per_page
        q = (
            select(Lesson)
            .options(joinedload(Lesson.subject))
            .where(Lesson.search_vector.op("@@")(ts_query))
            .order_by(func.ts_rank(Lesson.search_vector, ts_query).desc())
            .offset(offset).limit(self.per_page)
        )
        result = await session.execute(q)

        lessons = [
            LessonResult(
                title=l.title, url=l.url,
                description=l.description,
                subject=l.subject.name,
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
                        section=lesson.section,
                        topic=lesson.topic,
                        is_semantic=True,
                    )
                )
        return lessons

    async def hybrid_search(self, session: AsyncSession, query: str, page: int = 1) -> SearchResult:
        fts_lessons, fts_total = await self.fts_search(session, query, page=1)

        if fts_total >= self.fts_min_results:
            if page > 1:
                fts_lessons, _ = await self.fts_search(session, query, page=page)
            return SearchResult(query=query, lessons=fts_lessons, total=fts_total, page=page, per_page=self.per_page)

        # Not enough FTS results — add semantic search
        # Reuse fts_lessons from the first call (already page 1)
        fts_id_query = select(Lesson.id).where(
            Lesson.search_vector.op("@@")(_build_tsquery(query))
        )
        fts_id_result = await session.execute(fts_id_query)
        exclude_ids = [row[0] for row in fts_id_result.all()]

        semantic_lessons = await self.semantic_search(session, query, exclude_ids=exclude_ids)
        combined = fts_lessons + semantic_lessons
        total = len(combined)

        offset = (page - 1) * self.per_page
        page_lessons = combined[offset : offset + self.per_page]

        return SearchResult(query=query, lessons=page_lessons, total=total, page=page, per_page=self.per_page)
