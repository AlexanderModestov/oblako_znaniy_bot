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
    settings.enable_fuzzy_search = False
    settings.trigram_similarity_threshold = 0.3
    settings.trigram_title_weight = 1.0
    settings.fts_score_floor = 0.5
    return settings


@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
def test_search_service_has_required_methods(mock_settings):
    service = SearchService()
    assert hasattr(service, "fts_search")
    assert hasattr(service, "semantic_search")
    assert hasattr(service, "search_by_level")


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


# --- search_by_level tests ---

@pytest.mark.asyncio
@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
async def test_search_by_level_1_returns_and_fts(mock_settings):
    """Level 1 returns AND FTS results directly."""
    service = SearchService()
    lessons = [_make_lesson() for _ in range(3)]
    with patch.object(service, "fts_search", new_callable=AsyncMock) as mock_fts:
        mock_fts.return_value = (lessons, 3)
        result = await service.search_by_level(MagicMock(), "история", level=1)
    assert result.total == 3
    assert mock_fts.call_count == 1


@pytest.mark.asyncio
@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
async def test_search_by_level_2_combines_and_semantic(mock_settings):
    """Level 2 returns AND + semantic, deduplicated by URL."""
    service = SearchService()
    and_lesson = _make_lesson(subject="История")
    sem_lesson = LessonResult(
        title="Семантика", url="https://example.com/sem",
        subject="История", grade=8, section="Раздел", topic="Тема",
    )
    mock_session = MagicMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    with patch.object(service, "fts_search_all", new_callable=AsyncMock) as mock_all, \
         patch.object(service, "semantic_search", new_callable=AsyncMock) as mock_sem:
        mock_all.return_value = [and_lesson]
        mock_sem.return_value = [sem_lesson]
        result = await service.search_by_level(mock_session, "история", level=2)
    assert result.total == 2


@pytest.mark.asyncio
@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
async def test_search_by_level_2_deduplicates_by_url(mock_settings):
    """Level 2 deduplicates lessons with same URL."""
    service = SearchService()
    and_lesson = _make_lesson(subject="История")
    duplicate = LessonResult(
        title="Дубль", url=and_lesson.url,
        subject="История", grade=8, section="Раздел", topic="Тема",
    )
    mock_session = MagicMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    with patch.object(service, "fts_search_all", new_callable=AsyncMock) as mock_all, \
         patch.object(service, "semantic_search", new_callable=AsyncMock) as mock_sem:
        mock_all.return_value = [and_lesson]
        mock_sem.return_value = [duplicate]
        result = await service.search_by_level(mock_session, "история", level=2)
    assert result.total == 1


@pytest.mark.asyncio
@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
async def test_search_by_level_2_does_not_call_or_fts(mock_settings):
    """Level 2 must NOT invoke OR-FTS (that was level 3, now removed)."""
    service = SearchService()
    and_lesson = _make_lesson(subject="История")
    mock_session = MagicMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    with patch.object(service, "fts_search_all", new_callable=AsyncMock) as mock_all, \
         patch.object(service, "semantic_search", new_callable=AsyncMock) as mock_sem:
        mock_all.return_value = [and_lesson]
        mock_sem.return_value = []
        result = await service.search_by_level(mock_session, "история", level=2)
    assert result.total == 1
    # Critical: fts_search_all should be called exactly ONCE (AND only, no OR pass).
    assert mock_all.call_count == 1
    # And never with use_or=True (parameter removed, but double-check via kwargs).
    for call in mock_all.call_args_list:
        assert "use_or" not in call.kwargs


@pytest.mark.asyncio
@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
async def test_search_by_level_invalid_raises(mock_settings):
    service = SearchService()
    with pytest.raises(ValueError, match="Invalid search level"):
        await service.search_by_level(MagicMock(), "история", level=0)
    with pytest.raises(ValueError, match="Invalid search level"):
        await service.search_by_level(MagicMock(), "история", level=3)
