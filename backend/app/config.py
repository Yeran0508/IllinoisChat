from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Illinois Chat API"
    app_version: str = "0.1.0"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    postgres_db: str = "illinoischat"
    postgres_user: str = "illinoischat"
    postgres_password: str = Field(default="change-me", repr=False)
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    opensearch_host: str = "localhost"
    opensearch_port: int = 9200
    redis_host: str = "localhost"
    redis_port: int = 6379


@lru_cache
def get_settings() -> Settings:
    return Settings()
