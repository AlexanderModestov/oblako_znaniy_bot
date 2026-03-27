from unittest.mock import patch, MagicMock

from src.core.schemas import LessonResult, ClarifyQuestion
from src.core.services.search import SearchService, _build_tsquery


def _make_mock_settings():
    settings = MagicMock()
    settings.fts_min_results = 3
    settings.semantic_similarity_threshold = 0.75
    settings.results_per_page = 5
    settings.search_clarify_threshold = 10
    settings.openai_api_key = "test-key"
    return settings


@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
def test_search_service_has_required_methods(mock_settings):
    service = SearchService()
    assert hasattr(service, "fts_search")
    assert hasattr(service, "semantic_search")
    assert hasattr(service, "hybrid_search")


@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
def test_search_service_default_config(mock_settings):
    service = SearchService()
    assert service.fts_min_results == 3
    assert service.similarity_threshold == 0.75


def test_build_tsquery_single_word():
    expr = _build_tsquery("тангенс")
    sql = str(expr.compile())
    assert "plainto_tsquery" in sql
    assert "websearch_to_tsquery" not in sql


def test_build_tsquery_multiple_words():
    expr = _build_tsquery("тангенс котангенс")
    sql = str(expr.compile())
    assert "websearch_to_tsquery" in sql
    assert "plainto_tsquery" not in sql


def _make_lesson(subject="Математика", topic="Функции"):
    return LessonResult(
        title="Урок", url="https://example.com",
        subject=subject, topic=topic,
    )


@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
def test_check_clarification_below_threshold(mock_settings):
    service = SearchService()
    lessons = [_make_lesson() for _ in range(5)]
    result = service.check_clarification(lessons, stage="subject")
    assert result is None


@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
def test_check_clarification_single_subject(mock_settings):
    service = SearchService()
    lessons = [_make_lesson(subject="Математика") for _ in range(15)]
    result = service.check_clarification(lessons, stage="subject")
    assert result is None


@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
def test_check_clarification_subject_stage(mock_settings):
    service = SearchService()
    lessons = (
        [_make_lesson(subject="Математика") for _ in range(10)]
        + [_make_lesson(subject="Физика") for _ in range(5)]
    )
    result = service.check_clarification(lessons, stage="subject")
    assert result is not None
    assert result.stage == "subject"
    assert result.dominant_value == "Математика"
    assert result.total == 15


@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
def test_check_clarification_topic_stage(mock_settings):
    service = SearchService()
    lessons = (
        [_make_lesson(topic="Функции") for _ in range(8)]
        + [_make_lesson(topic="Уравнения") for _ in range(4)]
    )
    result = service.check_clarification(
        lessons, stage="topic", selected_subject="Математика",
    )
    assert result is not None
    assert result.stage == "topic"
    assert result.dominant_value == "Функции"
