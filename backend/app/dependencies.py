import uuid
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import SessionLocal, get_db
from app.ingestion.chunker import StructureAwareChunker
from app.ingestion.service import DocumentIngestionService
from app.ingestion.storage import LocalDocumentStorage
from app.retrieval.embeddings import EmbeddingProvider, FastEmbedBgeProvider
from app.retrieval.service import VectorRetrievalService


@lru_cache
def get_storage() -> LocalDocumentStorage:
    return LocalDocumentStorage(get_settings().document_storage_path)


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    return FastEmbedBgeProvider(
        model_name=settings.embedding_model,
        cache_dir=str(settings.embedding_cache_path),
    )


def get_document_service(
    session: Annotated[Session, Depends(get_db)],
    storage: Annotated[LocalDocumentStorage, Depends(get_storage)],
    embedder: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
) -> DocumentIngestionService:
    settings = get_settings()
    return DocumentIngestionService(
        session=session,
        storage=storage,
        embedder=embedder,
        chunker=StructureAwareChunker(
            settings.chunk_max_characters,
            settings.chunk_overlap_characters,
        ),
        max_upload_bytes=settings.max_upload_bytes,
    )


def get_retrieval_service(
    session: Annotated[Session, Depends(get_db)],
    embedder: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
) -> VectorRetrievalService:
    return VectorRetrievalService(
        session=session,
        embedder=embedder,
        ef_search=get_settings().hnsw_ef_search,
    )


def run_ingestion(version_id: uuid.UUID) -> None:
    with SessionLocal() as session:
        settings = get_settings()
        service = DocumentIngestionService(
            session=session,
            storage=get_storage(),
            embedder=get_embedding_provider(),
            chunker=StructureAwareChunker(
                settings.chunk_max_characters,
                settings.chunk_overlap_characters,
            ),
            max_upload_bytes=settings.max_upload_bytes,
        )
        service.ingest(version_id)
