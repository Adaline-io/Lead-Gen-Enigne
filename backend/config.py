"""Application configuration via Pydantic Settings.

Values are read from environment variables, falling back to a local ``.env``
file. ``SESSION_SECRET`` is mandatory and must be at least 32 characters — the
app refuses to start otherwise (see CLAUDE.md §15).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _baked_linkedin() -> dict:
    """Load baked-in LinkedIn creds from backend/secrets.py if present."""
    try:
        from backend import secrets as _s  # git-ignored, optional
        return {
            "user": getattr(_s, "LINKEDIN_USER", "") or "",
            "pass": getattr(_s, "LINKEDIN_PASS", "") or "",
            "cookie": getattr(_s, "LINKEDIN_COOKIE", "") or "",
            "jsessionid": getattr(_s, "LINKEDIN_JSESSIONID", "") or "",
        }
    except Exception:
        return {"user": "", "pass": "", "cookie": "", "jsessionid": ""}


_BAKED = _baked_linkedin()


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
    # gosom's -exit-on-inactivity: how long gosom waits with no new results
    # before finishing. Lower = searches finish sooner (the job stays "running"
    # at least this long). "45s", "1m", "2m"… are all valid.
    GOSOM_INACTIVITY: str = "45s"

    # LinkedIn source (optional). Uses the `linkedin-api` library for
    # industry/keyword company search. Off by default; falls back to demo data.
    # LinkedIn account is baked in via backend/secrets.py (git-ignored, shipped
    # in the bundle). Enabled automatically when credentials are present. .env
    # overrides everything below.
    LINKEDIN_ENABLED: bool = bool(_BAKED["user"] or _BAKED["cookie"])
    LINKEDIN_USER: str = _BAKED["user"]
    LINKEDIN_PASS: str = _BAKED["pass"]
    LINKEDIN_COOKIE: str = _BAKED["cookie"]
    LINKEDIN_JSESSIONID: str = _BAKED["jsessionid"]
    # Safety rails: max leads/day per source (0 = unlimited) + polite delay
    # between LinkedIn searches, to reduce the risk of account restrictions.
    LINKEDIN_DAILY_CAP: int = 80
    GMAPS_DAILY_CAP: int = 0
    LINKEDIN_THROTTLE_SECONDS: float = 2.0

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
