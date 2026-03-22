from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.core.models import Lesson, Section, Subject, Topic
from src.core.schemas import FilterState, LessonResult


class ContentService:
    async def get_subjects(self, session: AsyncSession) -> list[dict]:
        result = await session.execute(select(Subject).order_by(Subject.name))
        return [{"id": s.id, "name": s.name} for s in result.scalars().all()]

    async def get_grades_for_subject(self, session: AsyncSession, subject_id: int) -> list[int]:
        result = await session.execute(
            select(distinct(Lesson.grade))
            .where(Lesson.subject_id == subject_id)
            .order_by(Lesson.grade)
        )
        return list(result.scalars().all())

    async def get_sections(self, session: AsyncSession, subject_id: int, grade: int) -> list[dict]:
        result = await session.execute(
            select(distinct(Lesson.section_id))
            .where(Lesson.subject_id == subject_id, Lesson.grade == grade)
            .where(Lesson.section_id.is_not(None))
        )
        section_ids = list(result.scalars().all())
        if not section_ids:
            return []
        sections_result = await session.execute(
            select(Section).where(Section.id.in_(section_ids)).order_by(Section.name)
        )
        return [{"id": s.id, "name": s.name} for s in sections_result.scalars().all()]

    async def get_topics(self, session: AsyncSession, subject_id: int, grade: int, section_id: int) -> list[dict]:
        result = await session.execute(
            select(distinct(Lesson.topic_id))
            .where(Lesson.subject_id == subject_id, Lesson.grade == grade, Lesson.section_id == section_id)
            .where(Lesson.topic_id.is_not(None))
        )
        topic_ids = list(result.scalars().all())
        if not topic_ids:
            return []
        topics_result = await session.execute(
            select(Topic).where(Topic.id.in_(topic_ids)).order_by(Topic.name)
        )
        return [{"id": t.id, "name": t.name} for t in topics_result.scalars().all()]

    async def get_lessons(self, session: AsyncSession, filters: FilterState, page: int = 1, per_page: int = 5) -> tuple[list[LessonResult], int]:
        base_where = []
        if filters.subject_id:
            base_where.append(Lesson.subject_id == filters.subject_id)
        if filters.grade:
            base_where.append(Lesson.grade == filters.grade)
        if filters.section_id:
            base_where.append(Lesson.section_id == filters.section_id)
        if filters.topic_id:
            base_where.append(Lesson.topic_id == filters.topic_id)

        count_query = select(func.count(Lesson.id)).where(*base_where)
        count_result = await session.execute(count_query)
        total = count_result.scalar() or 0

        offset = (page - 1) * per_page
        query = (
            select(Lesson)
            .options(joinedload(Lesson.subject), joinedload(Lesson.section), joinedload(Lesson.topic))
            .where(*base_where)
            .order_by(Lesson.title)
            .offset(offset)
            .limit(per_page)
        )
        result = await session.execute(query)

        lessons = [
            LessonResult(
                title=l.title,
                url=l.url,
                description=l.description,
                subject=l.subject.name,
                section=l.section.name if l.section else None,
                topic=l.topic.name if l.topic else None,
            )
            for l in result.scalars().unique().all()
        ]
        return lessons, total
