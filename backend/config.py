"""Application configuration via Pydantic Settings.

Values are read from environment variables, falling back to a local ``.env``
file. ``SESSION_SECRET`` is mandatory and must be at least 32 characters — the
app refuses to start otherwise (see CLAUDE.md §15).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server
    SESSION_SECRET: str
    PORT: int = 8000

    # Database
    DATABASE_URL: str = "sqlite:///./data/leads.db"

    # Claude
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-haiku-4-5"

    # Scraper
    GOSOM_BIN: str = "/usr/local/bin/google-maps-scraper"
    SCRAPE_OUTPUT_DIR: str = "./data/scrapes"
    SCRAPE_TIMEOUT_SECONDS: int = 600
    # When gosom isn't installed, generate sample results so the full
    # find → review → approve flow works locally. Ignored once gosom is present.
    SCRAPER_DEMO: bool = True

    # Frontend (CORS)
    FRONTEND_ORIGIN: str = "http://localhost:5173"

    @field_validator("SESSION_SECRET")
    @classmethod
    def _validate_secret(cls, value: str) -> str:
        if not value or len(value) < 32:
            raise ValueError(
                "SESSION_SECRET must be set and at least 32 characters. "
                'Generate one with: python -c "import secrets; '
                'print(secrets.token_urlsafe(48))"'
            )
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
