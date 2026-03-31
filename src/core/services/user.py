from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import Region, School, Subject, User
from src.core.schemas import UserCreate


def _escape_like(query: str) -> str:
    return query.replace("%", r"\%").replace("_", r"\_")


class UserService:
    async def get_by_telegram_id(self, session: AsyncSession, telegram_id: int) -> User | None:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    async def get_by_max_user_id(self, session: AsyncSession, max_user_id: int) -> User | None:
        result = await session.execute(select(User).where(User.max_user_id == max_user_id))
        return result.scalar_one_or_none()

    async def create_user(self, session: AsyncSession, data: UserCreate) -> User:
        user = User(
            telegram_id=data.telegram_id,
            max_user_id=data.max_user_id,
            full_name=data.full_name,
            phone=data.phone,
            email=data.email,
            region_id=data.region_id,
            school_id=data.school_id,
            subjects=data.subjects,
            consent_given=data.consent_given,
            consent_at=datetime.now(timezone.utc) if data.consent_given else None,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    async def get_all_regions(self, session: AsyncSession) -> list[dict]:
        result = await session.execute(select(Region).order_by(Region.name))
        return [{"id": r.id, "name": r.name} for r in result.scalars().all()]

    async def search_regions(self, session: AsyncSession, query: str, limit: int = 8) -> list[dict]:
        escaped = _escape_like(query)
        result = await session.execute(
            select(Region).where(Region.name.ilike(f"%{escaped}%")).order_by(Region.name).limit(limit)
        )
        return [{"id": r.id, "name": r.name} for r in result.scalars().all()]

    async def get_municipalities_by_region(self, session: AsyncSession, region_id: int) -> list[dict]:
        result = await session.execute(
            select(School.municipality)
            .where(School.region_id == region_id, School.municipality.isnot(None))
            .distinct()
            .order_by(School.municipality)
        )
        return [{"id": i, "name": m} for i, m in enumerate(result.scalars().all())]

    async def get_schools_by_municipality(
        self, session: AsyncSession, region_id: int, municipality: str,
    ) -> list[dict]:
        result = await session.execute(
            select(School)
            .where(School.region_id == region_id, School.municipality == municipality)
            .order_by(School.name)
        )
        return [{"id": s.id, "name": s.name} for s in result.scalars().all()]

    async def get_schools_by_region(self, session: AsyncSession, region_id: int) -> list[dict]:
        result = await session.execute(
            select(School)
            .where(School.region_id == region_id)
            .order_by(School.name)
        )
        return [{"id": s.id, "name": s.name} for s in result.scalars().all()]

    async def search_schools(self, session: AsyncSession, region_id: int, query: str, limit: int = 8) -> list[dict]:
        escaped = _escape_like(query)
        result = await session.execute(
            select(School)
            .where(School.region_id == region_id, School.name.ilike(f"%{escaped}%"))
            .order_by(School.name)
            .limit(limit)
        )
        return [{"id": s.id, "name": s.name} for s in result.scalars().all()]

    async def create_school(self, session: AsyncSession, region_id: int, name: str, municipality: str | None = None) -> int:
        school = School(region_id=region_id, name=name.strip(), municipality=municipality)
        session.add(school)
        await session.commit()
        await session.refresh(school)
        return school.id

    async def get_all_subjects(self, session: AsyncSession) -> list[dict]:
        result = await session.execute(select(Subject).order_by(Subject.name))
        return [{"id": s.id, "name": s.name} for s in result.scalars().all()]

    async def get_user_count(self, session: AsyncSession) -> int:
        result = await session.execute(select(func.count(User.id)))
        return result.scalar() or 0
