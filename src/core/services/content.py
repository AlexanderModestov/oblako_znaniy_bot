from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.core.models import Lesson, Subject
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
            select(distinct(Lesson.section))
            .where(Lesson.subject_id == subject_id, Lesson.grade == grade)
            .where(Lesson.section.is_not(None))
            .order_by(Lesson.section)
        )
        names = list(result.scalars().all())
        return [{"id": i, "name": name} for i, name in enumerate(names)]

    async def get_topics(self, session: AsyncSession, subject_id: int, grade: int, section: str) -> list[dict]:
        result = await session.execute(
            select(distinct(Lesson.topic))
            .where(Lesson.subject_id == subject_id, Lesson.grade == grade, Lesson.section == section)
            .where(Lesson.topic.is_not(None))
            .order_by(Lesson.topic)
        )
        names = list(result.scalars().all())
        return [{"id": i, "name": name} for i, name in enumerate(names)]

    async def get_all_lessons(self, session: AsyncSession, filters: FilterState) -> list[LessonResult]:
        """Get all lessons matching filters without pagination."""
        base_where = []
        if filters.subject_id:
            base_where.append(Lesson.subject_id == filters.subject_id)
        if filters.grade:
            base_where.append(Lesson.grade == filters.grade)
        if filters.section:
            base_where.append(Lesson.section == filters.section)
        if filters.topic:
            base_where.append(Lesson.topic == filters.topic)

        na_last = case((Lesson.url == "N/A", 1), else_=0)
        query = (
            select(Lesson)
            .options(joinedload(Lesson.subject))
            .where(*base_where)
            .order_by(na_last, Lesson.title)
        )
        result = await session.execute(query)

        return [
            LessonResult(
                title=l.title,
                url=l.url,
                description=l.description,
                subject=l.subject.name,
                section=l.section,
                topic=l.topic,
            )
            for l in result.scalars().unique().all()
        ]

    async def get_lessons(self, session: AsyncSession, filters: FilterState, page: int = 1, per_page: int = 5) -> tuple[list[LessonResult], int]:
        base_where = []
        if filters.subject_id:
            base_where.append(Lesson.subject_id == filters.subject_id)
        if filters.grade:
            base_where.append(Lesson.grade == filters.grade)
        if filters.section:
            base_where.append(Lesson.section == filters.section)
        if filters.topic:
            base_where.append(Lesson.topic == filters.topic)

        count_query = select(func.count(Lesson.id)).where(*base_where)
        count_result = await session.execute(count_query)
        total = count_result.scalar() or 0

        offset = (page - 1) * per_page
        na_last = case((Lesson.url == "N/A", 1), else_=0)
        query = (
            select(Lesson)
            .options(joinedload(Lesson.subject))
            .where(*base_where)
            .order_by(na_last, Lesson.title)
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
                section=l.section,
                topic=l.topic,
            )
            for l in result.scalars().unique().all()
        ]
        return lessons, total
