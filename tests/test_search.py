import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.core.schemas import LessonResult, ClarifyOption, ClarifyResult
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


def test_build_tsquery_multiple_words_uses_and():
    expr = _build_tsquery("тангенс котангенс")
    compiled = expr.compile()
    sql = str(compiled)
    assert "plainto_tsquery" in sql
    # Verify multi-word string passed as single param (AND semantics — not split into OR)
    assert any("тангенс котангенс" in str(v) for v in compiled.params.values())


def test_build_tsquery_or_multiple_words():
    from src.core.services.search import _build_tsquery_or
    expr = _build_tsquery_or("тангенс котангенс")
    compiled = expr.compile()
    sql = str(compiled)
    assert "websearch_to_tsquery" in sql
    # OR is embedded in the string param passed to websearch_to_tsquery
    assert any("OR" in str(v).upper() for v in compiled.params.values())


def test_build_tsquery_or_single_word():
    from src.core.services.search import _build_tsquery_or
    expr = _build_tsquery_or("тангенс")
    sql = str(expr.compile())
    assert "plainto_tsquery" in sql


def _make_lesson(subject="Математика", grade=5, topic="Функции", section="Раздел 1"):
    return LessonResult(
        title="Урок", url="https://example.com",
        subject=subject, grade=grade, section=section, topic=topic,
    )


@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
def test_clarify_below_threshold_returns_none(mock_settings):
    service = SearchService()
    lessons = [_make_lesson() for _ in range(5)]
    assert service.check_clarification(lessons) is None


@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
def test_clarify_single_subject_single_grade_returns_none(mock_settings):
    service = SearchService()
    lessons = [_make_lesson(subject="Математика", grade=5) for _ in range(15)]
    assert service.check_clarification(lessons) is None


@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
def test_clarify_multiple_subjects(mock_settings):
    service = SearchService()
    lessons = (
        [_make_lesson(subject="Математика") for _ in range(10)]
        + [_make_lesson(subject="Физика") for _ in range(5)]
    )
    result = service.check_clarification(lessons)
    assert result is not None
    assert result.level == "subject"
    assert len(result.options) == 2
    assert result.options[0].value == "Математика"
    assert result.options[0].count == 10
    assert result.options[1].value == "Физика"
    assert result.options[1].count == 5
    assert result.total == 15


@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
def test_clarify_single_subject_multiple_grades(mock_settings):
    service = SearchService()
    lessons = (
        [_make_lesson(subject="Математика", grade=5) for _ in range(8)]
        + [_make_lesson(subject="Математика", grade=6) for _ in range(7)]
    )
    result = service.check_clarification(lessons)
    assert result is not None
    assert result.level == "grade"
    assert len(result.options) == 2
    assert result.options[0].value == "5"
    assert result.options[0].count == 8


@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
def test_clarify_single_subject_single_grade_multiple_topics(mock_settings):
    service = SearchService()
    lessons = (
        [_make_lesson(subject="Математика", grade=5, topic="Функции") for _ in range(7)]
        + [_make_lesson(subject="Математика", grade=5, topic="Уравнения") for _ in range(6)]
    )
    result = service.check_clarification(lessons)
    assert result is not None
    assert result.level == "topic"
    assert len(result.options) == 2


@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
def test_clarify_options_sorted_by_count_desc(mock_settings):
    service = SearchService()
    lessons = (
        [_make_lesson(subject="Физика") for _ in range(3)]
        + [_make_lesson(subject="Математика") for _ in range(9)]
        + [_make_lesson(subject="Химия") for _ in range(2)]
    )
    result = service.check_clarification(lessons)
    assert result.options[0].value == "Математика"
    assert result.options[1].value == "Физика"
    assert result.options[2].value == "Химия"


@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
def test_clarify_max_7_options(mock_settings):
    """More than 7 unique subjects -> only top 7 shown."""
    service = SearchService()
    subjects = [f"Предмет_{i}" for i in range(9)]
    lessons = []
    for i, subj in enumerate(subjects):
        lessons.extend([_make_lesson(subject=subj) for _ in range(10 - i)])
    result = service.check_clarification(lessons)
    assert len(result.options) <= 7


@pytest.mark.asyncio
@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
async def test_hybrid_search_uses_or_fallback_when_and_insufficient(mock_settings):
    """When AND FTS returns fewer than fts_min_results, OR FTS is used and returns enough results."""
    service = SearchService()

    or_lessons = [
        LessonResult(
            title=f"Вариант {i}", url=f"https://example.com/{i}",
            subject="Математика", grade=5, section="Раздел 1", topic="Тема 1",
        )
        for i in range(3)
    ]

    with patch.object(service, "fts_search", new_callable=AsyncMock) as mock_fts, \
         patch.object(service, "semantic_search", new_callable=AsyncMock) as mock_sem:

        mock_fts.side_effect = [
            ([], 0),                    # AND call → insufficient
            (or_lessons, 3),            # OR call → returns enough results
        ]
        mock_sem.return_value = []

        result = await service.hybrid_search(MagicMock(), "Петр 1")

    assert mock_fts.call_count == 2
    assert result.total == 3

    first_call, second_call = mock_fts.call_args_list
    assert first_call.kwargs.get("use_or", False) is False   # AND path
    assert second_call.kwargs.get("use_or", False) is True    # OR path


@pytest.mark.asyncio
@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
async def test_hybrid_search_uses_semantic_when_or_also_insufficient(mock_settings):
    """When both AND and OR FTS return fewer than fts_min_results, semantic search is used."""
    service = SearchService()

    semantic_lesson = LessonResult(
        title="Семантический урок", url="https://example.com/sem",
        subject="История", grade=8, section="Раздел", topic="Тема",
    )

    with patch.object(service, "fts_search", new_callable=AsyncMock) as mock_fts, \
         patch.object(service, "semantic_search", new_callable=AsyncMock) as mock_sem:

        mock_fts.side_effect = [
            ([], 0),  # AND call → insufficient
            ([], 0),  # OR call → insufficient
        ]
        mock_sem.return_value = [semantic_lesson]

        # Need to also mock session.execute for the exclude_ids query
        mock_session = MagicMock()
        mock_execute_result = MagicMock()
        mock_execute_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_execute_result)

        result = await service.hybrid_search(mock_session, "редкий запрос")

    assert mock_fts.call_count == 2
    assert mock_sem.call_count == 1
    assert result.total == 1
    assert result.lessons[0].title == "Семантический урок"


@pytest.mark.asyncio
@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
async def test_hybrid_search_uses_and_when_sufficient(mock_settings):
    """When AND FTS returns >= fts_min_results, OR is never called."""
    service = SearchService()

    lessons = [
        LessonResult(
            title=f"Урок {i}", url=f"https://example.com/{i}",
            subject="История", grade=8, section="Раздел", topic="Тема",
        )
        for i in range(5)
    ]

    with patch.object(service, "fts_search", new_callable=AsyncMock) as mock_fts, \
         patch.object(service, "semantic_search", new_callable=AsyncMock) as mock_sem:

        mock_fts.return_value = (lessons, 5)
        mock_sem.return_value = []

        result = await service.hybrid_search(MagicMock(), "история петр")

    assert mock_fts.call_count == 1
    assert result.total == 5
