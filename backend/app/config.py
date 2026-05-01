from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    # Required
    anthropic_api_key: str = Field(..., min_length=1)
    database_url: str = Field(..., min_length=1)
    jwt_secret: str = Field(..., min_length=32)

    # Defaults
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24
    cheap_model: str = "claude-haiku-4-5-20251001"
    strong_model: str = "claude-sonnet-4-6"
    embedding_model: str = "all-MiniLM-L6-v2"
    weather_url: str = "https://api.open-meteo.com/v1/forecast"
    weather_cache_ttl: int = 600
    discord_webhook_url: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
