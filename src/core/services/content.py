from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

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

    async def get_sections(self, session: AsyncSession, subject_id: int, grade: int) -> list[str]:
        result = await session.execute(
            select(distinct(Lesson.section))
            .where(Lesson.subject_id == subject_id, Lesson.grade == grade)
            .where(Lesson.section.is_not(None))
            .order_by(Lesson.section)
        )
        return list(result.scalars().all())

    async def get_topics(self, session: AsyncSession, subject_id: int, grade: int, section: str) -> list[str]:
        result = await session.execute(
            select(distinct(Lesson.topic))
            .where(Lesson.subject_id == subject_id, Lesson.grade == grade, Lesson.section == section)
            .where(Lesson.topic.is_not(None))
            .order_by(Lesson.topic)
        )
        return list(result.scalars().all())

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
        query = (
            select(Lesson).join(Subject)
            .where(*base_where)
            .order_by(Lesson.title)
            .offset(offset)
            .limit(per_page)
        )
        result = await session.execute(query)

        lessons = [
            LessonResult(
                title=l.title,
                lesson_type=l.lesson_type,
                url=l.url,
                subject=l.subject.name,
                section=l.section,
                topic=l.topic,
            )
            for l in result.scalars().all()
        ]
        return lessons, total
