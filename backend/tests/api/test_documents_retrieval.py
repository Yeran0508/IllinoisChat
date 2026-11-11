import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from app.dependencies import (
    get_cache_metrics,
    get_chat_service,
    get_document_service,
    get_retrieval_service,
)
from app.generation.models import ChatModelError
from app.generation.service import AnswerSentence, ChatResult, Citation
from app.ingestion.service import DocumentNotFoundError, RegistrationResult
from app.main import app
from app.retrieval.service import RetrievalResult
from fastapi.testclient import TestClient


@dataclass
class FakeDocumentService:
    missing: bool = False
    max_upload_bytes: int = 1024

    def register(self, **_kwargs) -> RegistrationResult:
        return RegistrationResult(
            document_id=uuid.UUID(int=1),
            version_id=uuid.UUID(int=2),
            status="pending",
            reused=False,
        )

    def get_document(self, document_id):
        if self.missing:
            raise DocumentNotFoundError("Document was not found")
        now = datetime.now(UTC)
        version = SimpleNamespace(
            id=uuid.UUID(int=2),
            status="completed",
            media_type="text/markdown",
            byte_size=10,
            content_sha256="a" * 64,
            embedding_model="test-model",
            error_message=None,
            created_at=now,
            completed_at=now,
        )
        return SimpleNamespace(
            id=document_id,
            course_id=uuid.UUID(int=3),
            title="Notes",
            source_name="notes.md",
            is_protected=False,
            versions=[version],
        )

    def delete_document(self, _document_id) -> None:
        if self.missing:
            raise DocumentNotFoundError("Document was not found")


class FakeRetrievalService:
    def search(self, **_kwargs) -> list[RetrievalResult]:
        return [
            RetrievalResult(
                chunk_id=uuid.UUID(int=4),
                document_id=uuid.UUID(int=1),
                version_id=uuid.UUID(int=2),
                title="Notes",
                source_name="notes.md",
                content="Vector search evidence.",
                page_number=1,
                section_path="Retrieval",
                score=0.9,
            )
        ]


class FakeChatService:
    def ask(self, **_kwargs) -> ChatResult:
        return ChatResult(
            request_id=uuid.UUID(int=9),
            status="answered",
            answer="Vector search uses embeddings.",
            sentences=[AnswerSentence("Vector search uses embeddings.", [1])],
            citations=[
                Citation(
                    citation_id=1,
                    chunk_id=uuid.UUID(int=4),
                    document_id=uuid.UUID(int=1),
                    version_id=uuid.UUID(int=2),
                    title="Notes",
                    source_name="notes.md",
                    page_number=1,
                    section_path="Retrieval",
                    evidence="Vector search evidence.",
                    score=0.9,
                )
            ],
            refusal_reason=None,
            retrieved_chunk_ids=[uuid.UUID(int=4)],
            model_name="test-model",
            latency_ms=12,
        )


class FakeCacheMetrics:
    def snapshot(self) -> dict:
        return {
            "hits": 8,
            "misses": 2,
            "hit_rate": 0.8,
            "stale_answer_rate": 0.0,
            "latency_ms": {"mean": 3.0, "p50": 2.0, "p95": 5.0},
        }


@pytest.fixture
def client():
    app.dependency_overrides[get_document_service] = lambda: FakeDocumentService()
    app.dependency_overrides[get_retrieval_service] = lambda: FakeRetrievalService()
    app.dependency_overrides[get_chat_service] = lambda: FakeChatService()
    app.dependency_overrides[get_cache_metrics] = lambda: FakeCacheMetrics()
    with TestClient(app) as value:
        yield value
    app.dependency_overrides.clear()


def test_register_get_ingest_delete_and_search_contracts(client) -> None:
    registered = client.post(
        "/api/v1/documents",
        data={"course_code": "CS", "course_name": "Course", "title": "Notes"},
        files={"file": ("notes.md", b"# Notes", "text/markdown")},
    )
    assert registered.status_code == 201
    document_id = registered.json()["document_id"]

    detail = client.get(f"/api/v1/documents/{document_id}")
    assert detail.status_code == 200
    assert detail.json()["versions"][0]["status"] == "completed"

    ingestion = client.post(f"/api/v1/documents/{document_id}/ingest")
    assert ingestion.status_code == 202
    assert ingestion.json()["status"] == "completed"

    search = client.post(
        "/api/v1/retrieval/search",
        json={"course_code": "CS", "query": "vector search", "top_k": 2},
    )
    assert search.status_code == 200
    assert search.json()["results"][0]["score"] == 0.9

    chat = client.post("/api/v1/chat", json={"course_code": "CS", "query": "vector search"})
    assert chat.status_code == 200
    assert chat.json()["sentences"][0]["citation_ids"] == [1]
    assert chat.json()["citations"][0]["chunk_id"] == str(uuid.UUID(int=4))

    evaluation = client.post("/api/v1/evaluations/run")
    assert evaluation.status_code == 200
    assert evaluation.json()["total_cases"] == 30
    assert evaluation.json()["review_status_counts"] == {"human_reviewed": 30}

    metrics = client.get("/api/v1/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["semantic_cache"]["hit_rate"] == 0.8

    deleted = client.delete(f"/api/v1/documents/{document_id}")
    assert deleted.status_code == 204


def test_missing_document_returns_404() -> None:
    app.dependency_overrides[get_document_service] = lambda: FakeDocumentService(missing=True)
    with TestClient(app) as client:
        response = client.get(f"/api/v1/documents/{uuid.uuid4()}")
    app.dependency_overrides.clear()

    assert response.status_code == 404


def test_chat_model_failure_returns_503_without_leaking_details() -> None:
    class FailingChatService:
        def ask(self, **_kwargs):
            raise ChatModelError("provider secret")

    app.dependency_overrides[get_chat_service] = lambda: FailingChatService()
    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"course_code": "CS", "query": "question"})
    app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"] == "The answer model is unavailable"
    assert "secret" not in response.text
