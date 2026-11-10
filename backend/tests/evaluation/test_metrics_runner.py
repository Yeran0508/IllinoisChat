import json
import uuid
from pathlib import Path

import pytest
from app.evaluation.metrics import ndcg_at_k, percentile, recall_at_k, summarize
from app.evaluation.runner import RetrievalEvaluator, load_dataset
from app.retrieval.service import RetrievalResult


def test_metrics_have_known_values() -> None:
    assert recall_at_k([1, 0, 1], 2, total_relevant=2) == 0.5
    assert ndcg_at_k([3, 1], 2, ideal_relevance=[3, 2, 1]) < 1.0
    assert ndcg_at_k([3, 2, 1], 3) == pytest.approx(1.0)
    assert percentile([10, 20, 30], 0.5) == 20
    assert summarize([10, 20, 30])["p95"] == pytest.approx(29)


def test_committed_dataset_has_30_unique_pending_review_cases() -> None:
    path = Path("data/evaluation/m2-v1.jsonl")
    cases = load_dataset(path)

    assert len(cases) == 30
    assert len({case.id for case in cases}) == 30
    assert {case.review_status for case in cases} == {"pending_human_review"}
    assert any(not case.answerable for case in cases)
    assert any(case.category == "cross-section" for case in cases)


class SectionRetriever:
    def search(self, *, course_code, query, top_k):
        del course_code, top_k
        section = "Relevant" if "answer" in query else "Wrong"
        return [
            RetrievalResult(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                version_id=uuid.uuid4(),
                title="Notes",
                source_name="notes.md",
                content="evidence",
                page_number=None,
                section_path=section,
                score=1.0,
            )
        ]


def test_evaluator_skips_unanswerable_cases_and_reports_review_status(tmp_path) -> None:
    lines = []
    for index in range(30):
        answerable = index < 29
        query = "answer this" if index == 0 else "miss"
        lines.append(
            json.dumps(
                {
                    "id": f"case-{index}",
                    "course_code": "CS",
                    "query": query,
                    "category": "test",
                    "answerable": answerable,
                    "relevant_sections": {"Relevant": 3} if answerable else {},
                    "review_status": "reviewed",
                }
            )
        )
    path = tmp_path / "evaluation.jsonl"
    path.write_text("\n".join(lines), encoding="utf-8")

    summary = RetrievalEvaluator(SectionRetriever()).run(path)

    assert summary.total_cases == 30
    assert summary.scored_cases == 29
    assert summary.recall_at_5 == pytest.approx(1 / 29)
    assert summary.review_status_counts == {"reviewed": 30}


class DuplicateSectionRetriever:
    def search(self, **_kwargs):
        return [
            RetrievalResult(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                version_id=uuid.uuid4(),
                title="Notes",
                source_name="notes.md",
                content="evidence",
                page_number=None,
                section_path="Relevant",
                score=1.0,
            )
            for _ in range(2)
        ]


def test_evaluator_counts_duplicate_chunks_from_one_section_once(tmp_path) -> None:
    lines = [
        json.dumps(
            {
                "id": f"case-{index}",
                "course_code": "CS",
                "query": "answer",
                "category": "test",
                "answerable": True,
                "relevant_sections": {"Relevant": 3},
                "review_status": "reviewed",
            }
        )
        for index in range(30)
    ]
    path = tmp_path / "evaluation.jsonl"
    path.write_text("\n".join(lines), encoding="utf-8")

    summary = RetrievalEvaluator(DuplicateSectionRetriever()).run(path)

    assert summary.ndcg_at_10 == pytest.approx(1.0)
