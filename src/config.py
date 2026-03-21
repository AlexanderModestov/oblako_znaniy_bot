from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bot_token: str
    admin_ids: list[int] = []
    database_url: str
    google_sheets_lessons_id: str
    google_sheets_schools_id: str
    google_service_account_json: str
    openai_api_key: str
    fts_min_results: int = 3
    semantic_similarity_threshold: float = 0.75
    results_per_page: int = 5

    class Config:
        env_file = ".env"

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v

    @property
    def sync_database_url(self) -> str:
        return self.database_url.replace("+asyncpg", "")


_settings = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
