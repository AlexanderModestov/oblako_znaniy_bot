import math

from pydantic import BaseModel, field_validator


class UserCreate(BaseModel):
    telegram_id: int | None = None
    full_name: str
    phone: str
    email: str | None = None
    region_id: int
    school_id: int
    subjects: list[int] = []

    @field_validator("full_name")
    @classmethod
    def name_must_have_two_words(cls, v: str) -> str:
        if len(v.strip().split()) < 2:
            raise ValueError("Введите имя и фамилию (минимум 2 слова)")
        return v.strip()


class LessonResult(BaseModel):
    title: str
    url: str
    description: str | None = None
    subject: str | None = None
    section: str | None = None
    topic: str | None = None
    is_semantic: bool = False


class SearchResult(BaseModel):
    query: str
    lessons: list[LessonResult]
    total: int
    page: int
    per_page: int

    @property
    def total_pages(self) -> int:
        return math.ceil(self.total / self.per_page) if self.total > 0 else 0


class FilterState(BaseModel):
    subject_id: int | None = None
    grade: int | None = None
    course_id: int | None = None
    section_id: int | None = None
    topic_id: int | None = None
