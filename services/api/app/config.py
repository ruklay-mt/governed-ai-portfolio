"""Runtime settings, read from environment variables (and `.env` in local development)."""

from functools import lru_cache
from typing import Annotated

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str | None = None

    @field_validator("database_url", mode="before")
    @classmethod
    def strip_database_url(cls, value: object) -> object:
        # Secrets pasted into a terminal often pick up a trailing newline.
        if isinstance(value, str):
            return value.strip() or None
        return value

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

    # Web: comma-separated in the environment, e.g. "https://a.example,https://b.example".
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
