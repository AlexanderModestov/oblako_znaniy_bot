import pytest
from pydantic import ValidationError

from src.core.schemas import (
    LessonResult,
    SearchResult,
    UserCreate,
    FilterState,
)


def test_user_create_valid():
    user = UserCreate(
        telegram_id=123456,
        full_name="Петров Иван Сергеевич",
        phone="+79001234567",
        region_id=1,
        school_id=1,
        subjects=[1, 2],
    )
    assert user.full_name == "Петров Иван Сергеевич"


def test_user_create_name_too_short():
    with pytest.raises(ValidationError):
        UserCreate(
            telegram_id=123,
            full_name="Иван",
            phone="+79001234567",
            region_id=1,
            school_id=1,
        )
    with pytest.raises(ValidationError):
        UserCreate(
            telegram_id=123,
            full_name="Иван Петров",
            phone="+79001234567",
            region_id=1,
            school_id=1,
        )


def test_lesson_result():
    lesson = LessonResult(
        title="Фотосинтез",
        lesson_type="Теория",
        url="https://gosuslugi.ru/123",
        subject="Биология",
        section="Растения",
        topic="Питание растений",
        is_semantic=False,
    )
    assert lesson.title == "Фотосинтез"
    assert lesson.is_semantic is False


def test_search_result_pagination():
    result = SearchResult(
        query="Никон",
        lessons=[],
        total=0,
        page=1,
        per_page=5,
    )
    assert result.total_pages == 0


def test_search_result_pagination_with_results():
    result = SearchResult(
        query="test",
        lessons=[],
        total=12,
        page=1,
        per_page=5,
    )
    assert result.total_pages == 3


def test_filter_state_defaults():
    state = FilterState()
    assert state.subject_id is None
    assert state.grade is None
    assert state.course_id is None
    assert state.section_id is None
    assert state.topic_id is None
