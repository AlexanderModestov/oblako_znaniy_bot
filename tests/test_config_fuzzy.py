from src.config import Settings


def _make_settings() -> Settings:
    return Settings(
        bot_token="x",
        database_url="postgresql+asyncpg://u:p@h:5432/d",
        google_sheets_lessons_id="x",
        google_sheets_schools_id="x",
        google_service_account_json="{}",
        openai_api_key="x",
    )


def test_fuzzy_search_defaults():
    s = _make_settings()
    assert s.enable_fuzzy_search is True
