import math

from pydantic import BaseModel, field_validator


class UserCreate(BaseModel):
    telegram_id: int | None = None
    max_user_id: int | None = None
    full_name: str
    phone: str
    email: str | None = None
    region_id: int
    school_id: int | None = None
    subjects: list[int] = []
    consent_given: bool = False

    @field_validator("full_name")
    @classmethod
    def name_must_have_three_words(cls, v: str) -> str:
        if len(v.strip().split()) < 3:
            raise ValueError("Введите полное ФИО (Фамилия Имя Отчество)")
        return v.strip()


class LessonResult(BaseModel):
    title: str
    url: str
    description: str | None = None
    subject: str | None = None
    grade: int | None = None
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


class ClarifyQuestion(BaseModel):
    stage: str              # "subject" or "topic"
    dominant_value: str     # e.g. "Математика"
    total: int              # total results count
    message: str            # question text for user


class FilterState(BaseModel):
    subject_id: int | None = None
    grade: int | None = None
    section: str | None = None
    topic: str | None = None
