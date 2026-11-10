import uuid
from dataclasses import dataclass

import pytest
from app.retrieval.hybrid import HybridRetrievalService
from app.retrieval.service import RetrievalResult


def result(value: int, score: float, source: str) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=uuid.UUID(int=value),
        document_id=uuid.UUID(int=100 + value),
        version_id=uuid.UUID(int=200 + value),
        title=f"Title {value}",
        source_name="notes.md",
        content=f"passage {value}",
        page_number=None,
        section_path="Section",
        score=score,
        retrieval_metadata={f"{source}_score": score},
    )


@dataclass
class FakeRetriever:
    results: list[RetrievalResult]

    def search(self, **_kwargs) -> list[RetrievalResult]:
        return self.results


class FakeReranker:
    model_name = "test-reranker"

    def score(self, _query, documents):
        return [1.0 if value == "passage 2" else 0.1 for value in documents]


def test_rrf_deduplicates_and_cross_encoder_reranks() -> None:
    service = HybridRetrievalService(
        vector=FakeRetriever([result(1, 0.9, "vector"), result(2, 0.8, "vector")]),
        lexical=FakeRetriever([result(2, 5.0, "bm25"), result(3, 4.0, "bm25")]),
        reranker=FakeReranker(),
        candidate_k=3,
        rrf_rank_constant=60,
    )

    results = service.search(course_code="CS", query="question", top_k=2)

    assert [value.chunk_id for value in results] == [uuid.UUID(int=2), uuid.UUID(int=1)]
    assert results[0].retrieval_metadata["vector_rank"] == 2
    assert results[0].retrieval_metadata["bm25_rank"] == 1
    assert results[0].retrieval_metadata["reranker_model"] == "test-reranker"


def test_hybrid_validates_configuration_and_reranker_count() -> None:
    with pytest.raises(ValueError, match="candidate_k"):
        HybridRetrievalService(
            vector=FakeRetriever([]),
            lexical=FakeRetriever([]),
            reranker=FakeReranker(),
            candidate_k=0,
        )
    service = HybridRetrievalService(
        vector=FakeRetriever([result(1, 1.0, "vector")]),
        lexical=FakeRetriever([]),
        reranker=type(
            "BadReranker",
            (),
            {"model_name": "bad", "score": lambda *_args: []},
        )(),
    )
    with pytest.raises(ValueError, match="score count"):
        service.search(course_code="CS", query="question", top_k=1)
