from app.config import Settings
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db


def test_database_url_encodes_special_password_characters() -> None:
    settings = Settings(postgres_password="p@ss:word")

    assert "p%40ss%3Aword" in settings.database_url
    assert settings.database_url.startswith("postgresql+psycopg://")


def test_metadata_contains_document_version_and_chunk_tables() -> None:
    assert set(Base.metadata.tables) == {
        "courses",
        "documents",
        "document_versions",
        "chunks",
        "chat_request_logs",
    }

    chunks = Base.metadata.tables["chunks"]
    assert str(chunks.c.embedding.type) == "VECTOR(384)"
    assert "ix_chunks_embedding_hnsw" in {index.name for index in chunks.indexes}


def test_database_dependency_yields_a_session_without_connecting() -> None:
    dependency = get_db()
    session = next(dependency)

    assert session.get_bind().dialect.name == "postgresql"

    dependency.close()
