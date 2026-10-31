"""App settings, loaded from environment variables (and `.env` in local development).

Everything configurable or secret lives here, typed and validated, so a bad or
missing value fails loudly when settings are loaded instead of deep inside a review.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    ai_provider: Literal["none", "fake", "github"] = "none"

    # Shared secret GitHub uses to sign webhooks (HMAC). Required, and long enough
    # that it can't be guessed. Generate one with:
    #   python -c "import secrets; print(secrets.token_hex(32))"
    github_webhook_secret: SecretStr = Field(min_length=32)


@lru_cache
def get_settings() -> Settings:
    """Return the settings, loaded once and reused (env is read on the first call)."""
    return Settings()
