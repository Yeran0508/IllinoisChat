from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


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
    postgres_password: SecretStr = Field(default=SecretStr("change-me"), repr=False)
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    opensearch_host: str = "localhost"
    opensearch_port: int = 9200
    redis_host: str = "localhost"
    redis_port: int = 6379

    chunk_max_characters: int = 1200
    chunk_overlap_characters: int = 150
    document_storage_path: Path = Path("data/uploads")
    max_upload_bytes: int = 20 * 1024 * 1024

    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_cache_path: Path = Path("data/models")
    hnsw_ef_search: int = 64
    retrieval_top_k: int = 5
    retrieval_min_score: float = 0.35

    llm_base_url: str = "http://host.docker.internal:11434/v1"
    llm_api_key: SecretStr = Field(default=SecretStr(""), repr=False)
    llm_model: str = "qwen3:4b"
    llm_timeout_seconds: float = 60.0

    @property
    def database_url(self) -> str:
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        ).render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
