import uuid
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import SessionLocal, get_db
from app.generation.audit import SqlAlchemyChatAuditLogger
from app.generation.models import ChatModelProvider, OpenAICompatibleChatModel
from app.generation.service import GroundedChatService
from app.ingestion.chunker import StructureAwareChunker
from app.ingestion.service import DocumentIngestionService
from app.ingestion.storage import LocalDocumentStorage
from app.retrieval.advanced import (
    IterativeRetrievalService,
    ModelEvidenceSufficiencyEvaluator,
    ModelQuestionDecomposer,
)
from app.retrieval.embeddings import EmbeddingProvider, FastEmbedBgeProvider
from app.retrieval.hybrid import HybridRetrievalService
from app.retrieval.lexical import ChunkLexicalIndex, OpenSearchBM25Index
from app.retrieval.reranking import FastEmbedCrossEncoderReranker, Reranker
from app.retrieval.service import RetrievalService, VectorRetrievalService
from app.safety.assignment import SqlAlchemyProtectedAssignmentMatcher
from app.safety.support import ModelSentenceSupportValidator


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


@lru_cache
def get_lexical_index() -> ChunkLexicalIndex:
    settings = get_settings()
    return OpenSearchBM25Index(
        base_url=f"http://{settings.opensearch_host}:{settings.opensearch_port}",
        index_name=settings.opensearch_index,
        timeout_seconds=settings.opensearch_timeout_seconds,
    )


@lru_cache
def get_reranker() -> Reranker:
    settings = get_settings()
    return FastEmbedCrossEncoderReranker(
        model_name=settings.reranker_model,
        cache_dir=str(settings.embedding_cache_path),
    )


def get_document_service(
    session: Annotated[Session, Depends(get_db)],
    storage: Annotated[LocalDocumentStorage, Depends(get_storage)],
    embedder: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
    lexical_index: Annotated[ChunkLexicalIndex, Depends(get_lexical_index)],
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
        lexical_index=lexical_index,
    )


def get_vector_retrieval_service(
    session: Annotated[Session, Depends(get_db)],
    embedder: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
) -> VectorRetrievalService:
    return VectorRetrievalService(
        session=session,
        embedder=embedder,
        ef_search=get_settings().hnsw_ef_search,
    )


def get_retrieval_service(
    vector: Annotated[VectorRetrievalService, Depends(get_vector_retrieval_service)],
    lexical: Annotated[ChunkLexicalIndex, Depends(get_lexical_index)],
    reranker: Annotated[Reranker, Depends(get_reranker)],
) -> RetrievalService:
    settings = get_settings()
    base = HybridRetrievalService(
        vector=vector,
        lexical=lexical,
        reranker=reranker,
        candidate_k=settings.retrieval_candidate_k,
        rrf_rank_constant=settings.rrf_rank_constant,
    )
    model = get_chat_model()
    return IterativeRetrievalService(
        base=base,
        decomposer=ModelQuestionDecomposer(
            model=model,
            max_subquestions=settings.advanced_retrieval_max_subquestions,
        ),
        sufficiency=ModelEvidenceSufficiencyEvaluator(model=model),
        max_steps=settings.advanced_retrieval_max_steps,
        max_subquestions=settings.advanced_retrieval_max_subquestions,
        per_query_k=settings.advanced_retrieval_per_query_k,
        rrf_rank_constant=settings.rrf_rank_constant,
    )


@lru_cache
def get_chat_model() -> ChatModelProvider:
    settings = get_settings()
    return OpenAICompatibleChatModel(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key.get_secret_value(),
        model_name=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )


def get_chat_service(
    session: Annotated[Session, Depends(get_db)],
    retrieval: Annotated[RetrievalService, Depends(get_retrieval_service)],
    model: Annotated[ChatModelProvider, Depends(get_chat_model)],
) -> GroundedChatService:
    settings = get_settings()
    return GroundedChatService(
        retrieval=retrieval,
        model=model,
        audit=SqlAlchemyChatAuditLogger(session),
        top_k=settings.retrieval_top_k,
        minimum_score=settings.retrieval_min_score,
        assignment_matcher=SqlAlchemyProtectedAssignmentMatcher(
            session,
            get_embedding_provider(),
            minimum_score=settings.protected_assignment_min_score,
        ),
        sentence_support=ModelSentenceSupportValidator(model),
        hint_level=settings.homework_hint_level,
        remove_unsupported_sentences=settings.remove_unsupported_sentences,
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
            lexical_index=get_lexical_index(),
        )
        service.ingest(version_id)
