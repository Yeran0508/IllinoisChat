import hashlib
import math
import os
import re
from collections.abc import Sequence
from pathlib import Path

import pytest
from app.caching.semantic import SqlAlchemyCorpusFingerprintProvider
from app.db.models import ChatRequestLog, Chunk, Course, DocumentVersion
from app.db.session import SessionLocal
from app.evaluation.safety import load_safety_dataset
from app.generation.audit import SqlAlchemyChatAuditLogger
from app.generation.service import GroundedChatService
from app.ingestion.chunker import StructureAwareChunker
from app.ingestion.service import DocumentIngestionService
from app.ingestion.storage import LocalDocumentStorage
from app.retrieval.service import VectorRetrievalService
from app.safety.assignment import SqlAlchemyProtectedAssignmentMatcher
from sqlalchemy import delete, func, select

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="requires migrated PostgreSQL",
    ),
]


class DeterministicEmbeddingProvider:
    model_name = "test-hash-embedding"
    dimension = 384

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            index = int.from_bytes(hashlib.sha256(token.encode()).digest()[:2]) % self.dimension
            vector[index] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class RecordingLexicalIndex:
    def __init__(self) -> None:
        self.versions = {}
        self.deleted_documents = []
        self.deleted_versions = []

    def replace_version(self, version_id, chunks) -> None:
        self.versions[version_id] = list(chunks)

    def delete_document(self, document_id) -> None:
        self.deleted_documents.append(document_id)

    def delete_version(self, version_id) -> None:
        self.deleted_versions.append(version_id)

    def search(self, **_kwargs):
        return []


@pytest.fixture
def db_session():
    with SessionLocal() as session:
        session.execute(delete(ChatRequestLog))
        session.execute(delete(Course))
        session.commit()
        yield session
        session.rollback()
        session.execute(delete(ChatRequestLog))
        session.execute(delete(Course))
        session.commit()


@pytest.fixture
def ingestion_service(db_session, tmp_path):
    return DocumentIngestionService(
        session=db_session,
        storage=LocalDocumentStorage(tmp_path),
        embedder=DeterministicEmbeddingProvider(),
        chunker=StructureAwareChunker(max_characters=200, overlap_characters=20),
        max_upload_bytes=10_000,
        lexical_index=RecordingLexicalIndex(),
    )


def test_register_ingest_reuse_search_and_delete(db_session, ingestion_service) -> None:
    content = b"""# Vector Search

Vector search retrieves semantically related course passages.

## HNSW

HNSW is an approximate nearest-neighbor graph index.
"""
    first = ingestion_service.register(
        course_code="CS-TEST",
        course_name="Test Course",
        title="Retrieval Notes",
        source_name="retrieval.md",
        media_type="text/markdown",
        content=content,
    )
    repeated = ingestion_service.register(
        course_code="CS-TEST",
        course_name="Test Course",
        title="Retrieval Notes",
        source_name="retrieval.md",
        media_type="text/markdown",
        content=content,
    )

    assert repeated.reused is True
    assert repeated.version_id == first.version_id

    version = ingestion_service.ingest(first.version_id)
    assert version.status == "completed"
    assert version.embedding_model == "test-hash-embedding"
    assert (
        db_session.scalar(
            select(func.count()).select_from(Chunk).where(Chunk.document_version_id == version.id)
        )
        == 4
    )
    indexed = ingestion_service.lexical_index.versions[version.id]
    assert len(indexed) == 4
    assert all(value.course_code == "CS-TEST" for value in indexed)

    retrieval = VectorRetrievalService(
        db_session,
        DeterministicEmbeddingProvider(),
        ef_search=64,
    )
    results = retrieval.search(course_code="CS-TEST", query="HNSW graph index", top_k=2)

    assert results
    assert results[0].document_id == first.document_id
    assert "HNSW" in results[0].content
    assert 0.0 <= results[0].score <= 1.0

    storage_key = version.storage_key
    ingestion_service.delete_document(first.document_id)
    assert first.document_id in ingestion_service.lexical_index.deleted_documents
    assert db_session.get(DocumentVersion, first.version_id) is None
    with pytest.raises(FileNotFoundError):
        ingestion_service.storage.read(storage_key)


def test_ingestion_failure_is_persisted(ingestion_service, db_session) -> None:
    registered = ingestion_service.register(
        course_code="CS-TEST",
        course_name="Test Course",
        title="Broken Notes",
        source_name="broken.md",
        media_type="text/markdown",
        content=b"```python\nprint('missing closing fence')",
    )

    with pytest.raises(ValueError, match="unclosed fenced code block"):
        ingestion_service.ingest(registered.version_id)

    db_session.expire_all()
    version = db_session.get(DocumentVersion, registered.version_id)
    assert version is not None
    assert version.status == "failed"
    assert "unclosed fenced code block" in (version.error_message or "")
    assert registered.version_id in ingestion_service.lexical_index.deleted_versions


def test_corpus_fingerprint_changes_after_new_completed_version(
    ingestion_service, db_session
) -> None:
    first = ingestion_service.register(
        course_code="CS-CACHE",
        course_name="Cache Course",
        title="Notes",
        source_name="notes.md",
        media_type="text/markdown",
        content=b"# Version one\n\nInitial material.",
    )
    ingestion_service.ingest(first.version_id)
    fingerprints = SqlAlchemyCorpusFingerprintProvider(db_session)
    before = fingerprints.fingerprint("CS-CACHE")

    second = ingestion_service.register(
        course_code="CS-CACHE",
        course_name="Cache Course",
        title="Notes",
        source_name="notes.md",
        media_type="text/markdown",
        content=b"# Version two\n\nUpdated material.",
    )
    ingestion_service.ingest(second.version_id)

    assert fingerprints.fingerprint("CS-CACHE") != before


def test_protected_assignment_is_isolated_from_normal_retrieval(
    ingestion_service, db_session
) -> None:
    registered = ingestion_service.register(
        course_code="CS-SAFETY",
        course_name="Safety Course",
        title="Homework 1",
        source_name="homework-1.md",
        media_type="text/markdown",
        content=b"# Question 2\n\nImplement reciprocal rank fusion for two ranked lists.",
        is_protected=True,
    )
    ingestion_service.ingest(registered.version_id)

    assert ingestion_service.lexical_index.versions[registered.version_id] == []
    retrieval = VectorRetrievalService(db_session, DeterministicEmbeddingProvider(), ef_search=64)
    assert (
        retrieval.search(
            course_code="CS-SAFETY", query="implement reciprocal rank fusion", top_k=5
        )
        == []
    )

    matcher = SqlAlchemyProtectedAssignmentMatcher(
        db_session,
        DeterministicEmbeddingProvider(),
        minimum_score=0.2,
    )
    match = matcher.match(
        course_code="CS-SAFETY",
        query="Complete Homework 1 Question 2 for reciprocal rank fusion",
    )
    assert match is not None
    assert match.document_id == registered.document_id


def test_human_reviewed_safety_dataset_has_no_detection_regression(
    ingestion_service, db_session
) -> None:
    registered = ingestion_service.register(
        course_code="CS-RAG",
        course_name="Synthetic RAG Safety",
        title="Homework 1",
        source_name="m3-protected-homework.md",
        media_type="text/markdown",
        content=Path("data/sample/m3-protected-homework.md").read_bytes(),
        is_protected=True,
    )
    ingestion_service.ingest(registered.version_id)
    matcher = SqlAlchemyProtectedAssignmentMatcher(
        db_session,
        DeterministicEmbeddingProvider(),
        minimum_score=0.82,
    )

    for case in load_safety_dataset(Path("data/evaluation/m3-safety-v1.jsonl")):
        detected = matcher.match(course_code=case.course_code, query=case.query) is not None
        assert detected is case.expected_protected, case.id


def test_ingestion_to_grounded_answer_and_private_audit(db_session, ingestion_service) -> None:
    registered = ingestion_service.register(
        course_code="CS-TEST",
        course_name="Test Course",
        title="HNSW Notes",
        source_name="hnsw.md",
        media_type="text/markdown",
        content=b"# HNSW\n\nHNSW is an approximate nearest-neighbor graph index.",
    )
    ingestion_service.ingest(registered.version_id)
    retrieval = VectorRetrievalService(db_session, DeterministicEmbeddingProvider(), ef_search=64)

    class GroundedModel:
        model_name = "integration-static-model"

        def complete(self, **_kwargs) -> str:
            return (
                '{"sufficient":true,"sentences":['
                '{"text":"HNSW is an approximate nearest-neighbor graph index.",'
                '"citation_ids":[1]}]}'
            )

    service = GroundedChatService(
        retrieval=retrieval,
        model=GroundedModel(),
        audit=SqlAlchemyChatAuditLogger(db_session),
        top_k=2,
        minimum_score=0.0,
    )
    raw_query = "What is HNSW?"
    result = service.ask(course_code="CS-TEST", query=raw_query)

    assert result.status == "answered"
    assert result.citations[0].chunk_id in result.retrieved_chunk_ids
    log = db_session.get(ChatRequestLog, result.request_id)
    assert log is not None
    assert log.outcome == "answered"
    assert log.query_sha256 == hashlib.sha256(raw_query.encode()).hexdigest()
    assert raw_query not in str(log.__dict__)
    assert log.cited_chunk_ids == [str(result.citations[0].chunk_id)]
