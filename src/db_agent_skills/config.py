from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "northwind.db"
DEFAULT_DATABASE_URL = f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"
DEFAULT_MODEL = "openai/gpt-6-astra"


class Settings(BaseSettings):
    model: str = DEFAULT_MODEL
    openrouter_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="OPENROUTER_API_KEY",
    )
    database_url: str = DEFAULT_DATABASE_URL

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        env_prefix="DB_AGENT_",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
