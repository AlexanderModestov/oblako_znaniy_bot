from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from src.core.services.search import SearchService


def _mock_settings(**overrides):
    def factory():
        m = MagicMock()
        m.fts_min_results = 3
        m.semantic_similarity_threshold = 0.75
        m.results_per_page = 5
        m.search_clarify_threshold = 10
        m.enable_fuzzy_search = True
        m.trigram_similarity_threshold = 0.3
        m.trigram_title_weight = 1.0
        m.fts_score_floor = 0.5
        for k, v in overrides.items():
            setattr(m, k, v)
        return m
    return factory


@pytest.mark.asyncio
@patch("src.core.services.search.get_settings", side_effect=_mock_settings())
async def test_level_1_uses_fuzzy_when_flag_on(_):
    service = SearchService()
    with patch.object(service, "fts_search_fuzzy", new_callable=AsyncMock) as m_fuzzy, \
         patch.object(service, "fts_search", new_callable=AsyncMock) as m_strict:
        m_fuzzy.return_value = ([], 0)
        await service.search_by_level(MagicMock(), "q", level=1)
    assert m_fuzzy.call_count == 1
    assert m_strict.call_count == 0


@pytest.mark.asyncio
@patch("src.core.services.search.get_settings", side_effect=_mock_settings(enable_fuzzy_search=False))
async def test_level_1_uses_strict_when_flag_off(_):
    service = SearchService()
    with patch.object(service, "fts_search_fuzzy", new_callable=AsyncMock) as m_fuzzy, \
         patch.object(service, "fts_search", new_callable=AsyncMock) as m_strict:
        m_strict.return_value = ([], 0)
        await service.search_by_level(MagicMock(), "q", level=1)
    assert m_strict.call_count == 1
    assert m_fuzzy.call_count == 0
