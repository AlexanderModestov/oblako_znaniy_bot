from src.core.services.search import _normalize_tokens, _build_or_tsquery_string


def test_normalize_splits_and_lowercases():
    assert _normalize_tokens("Теорема Пифагора") == ["теорема", "пифагора"]


def test_normalize_drops_single_char_non_digit():
    assert _normalize_tokens("а теорема") == ["теорема"]


def test_normalize_keeps_digits():
    assert _normalize_tokens("7 класс") == ["7", "класс"]


def test_normalize_strips_tsquery_specials():
    assert _normalize_tokens("теорема & | ! ( ) : *") == ["теорема"]


def test_normalize_empty_string():
    assert _normalize_tokens("   ") == []


def test_build_or_tsquery_single_token():
    assert _build_or_tsquery_string(["теорема"]) == "теорема"


def test_build_or_tsquery_multi_tokens():
    assert _build_or_tsquery_string(["теорема", "пифагора"]) == "теорема | пифагора"


def test_build_or_tsquery_empty():
    assert _build_or_tsquery_string([]) == ""


def test_build_or_tsquery_digit_no_prefix():
    assert _build_or_tsquery_string(["2", "закон"]) == "2 | закон"


def test_build_or_tsquery_all_digits():
    assert _build_or_tsquery_string(["7", "11"]) == "7 | 11"


def test_normalize_filters_russian_stopwords():
    assert _normalize_tokens("лабораторные по физике") == ["лабораторные", "физике"]


def test_normalize_keeps_only_stopwords_returns_empty():
    assert _normalize_tokens("по на в") == []
