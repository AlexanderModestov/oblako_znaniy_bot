from unittest.mock import patch, MagicMock

from src.core.services.search import SearchService


def _make_mock_settings():
    settings = MagicMock()
    settings.fts_min_results = 3
    settings.semantic_similarity_threshold = 0.75
    settings.results_per_page = 5
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
