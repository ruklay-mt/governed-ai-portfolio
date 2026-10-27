"""Runtime settings, read from environment variables (and `.env` in local development)."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str | None = None

    # Models: names always come from the environment, never from code (CLAUDE.md rule 5).
    anthropic_api_key: SecretStr | None = None
    model_main: str | None = None
    model_small: str | None = None
    voyage_api_key: SecretStr | None = None
    embedding_model: str | None = None

    # Tracing
    langfuse_host: str | None = None
    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None

    # Cost guards (spec §16)
    daily_budget_usd: float = 1.00

    # Web
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
