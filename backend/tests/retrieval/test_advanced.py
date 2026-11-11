import uuid
from dataclasses import dataclass, field

from app.retrieval.advanced import (
    IterativeRetrievalService,
    ModelEvidenceSufficiencyEvaluator,
    ModelQuestionDecomposer,
    SufficiencyOutput,
)
from app.retrieval.service import RetrievalResult


def result(identity: int, section: str, score: float = 0.9) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=uuid.UUID(int=identity),
        document_id=uuid.UUID(int=100 + identity),
        version_id=uuid.UUID(int=200 + identity),
        title="Notes",
        source_name="notes.md",
        content=f"Evidence for {section}",
        page_number=None,
        section_path=section,
        score=score,
    )


@dataclass
class QueryRetrieval:
    values: dict[str, list[RetrievalResult]]
    calls: list[str] = field(default_factory=list)

    def search(self, *, course_code, query, top_k):
        del course_code
        self.calls.append(query)
        return self.values.get(query, [])[:top_k]


@dataclass
class StaticDecomposer:
    values: list[str]

    def decompose(self, query):
        del query
        return self.values


@dataclass
class SequencedSufficiency:
    values: list[SufficiencyOutput]
    calls: int = 0

    def evaluate(self, **_kwargs):
        value = self.values[self.calls]
        self.calls += 1
        return value


def test_iterative_retrieval_decomposes_retries_deduplicates_and_traces() -> None:
    base = QueryRetrieval(
        {
            "What is versioning?": [result(1, "Versioning"), result(3, "Shared")],
            "How does cache invalidation use it?": [result(3, "Shared")],
            "corpus-aware cache invalidation": [result(2, "Caching")],
        }
    )
    sufficiency = SequencedSufficiency(
        [
            SufficiencyOutput(
                sufficient=False,
                missing_subquestions=["How does cache invalidation use it?"],
                follow_up_queries=["corpus-aware cache invalidation"],
            ),
            SufficiencyOutput(sufficient=True),
        ]
    )
    service = IterativeRetrievalService(
        base=base,
        decomposer=StaticDecomposer(
            ["What is versioning?", "How does cache invalidation use it?"]
        ),
        sufficiency=sufficiency,
        max_steps=2,
        per_query_k=5,
    )

    output = service.search_with_trace(course_code="CS", query="cross topic", top_k=5)

    assert {item.chunk_id for item in output.results} == {
        uuid.UUID(int=1),
        uuid.UUID(int=2),
        uuid.UUID(int=3),
    }
    assert output.results[0].chunk_id == uuid.UUID(int=3)
    assert output.trace.sufficient is True
    assert output.trace.steps_used == 2
    assert output.trace.stopped_reason == "sufficient"
    assert [attempt.query for attempt in output.trace.attempts] == [
        "What is versioning?",
        "How does cache invalidation use it?",
        "corpus-aware cache invalidation",
    ]


def test_iterative_retrieval_stops_without_follow_up_and_respects_subquestion_limit() -> None:
    base = QueryRetrieval({"one": []})
    service = IterativeRetrievalService(
        base=base,
        decomposer=StaticDecomposer(["one", "two", "three"]),
        sufficiency=SequencedSufficiency(
            [SufficiencyOutput(sufficient=False, missing_subquestions=["one"])]
        ),
        max_steps=2,
        max_subquestions=1,
    )

    output = service.search_with_trace(course_code="CS", query="question", top_k=5)

    assert base.calls == ["one"]
    assert output.trace.stopped_reason == "no_follow_up_queries"
    assert output.trace.steps_used == 1


@dataclass
class StaticModel:
    responses: list[str]
    model_name: str = "static"

    def complete(self, **_kwargs):
        return self.responses.pop(0)


def test_model_adapters_fail_closed_and_bound_outputs() -> None:
    model = StaticModel(
        [
            "not-json",
            '{"sufficient":false,"missing_subquestions":["missing"],'
            '"follow_up_queries":["one","two","three"]}',
        ]
    )
    decomposer = ModelQuestionDecomposer(model, max_subquestions=2)
    evaluator = ModelEvidenceSufficiencyEvaluator(model, max_follow_up_queries=2)

    assert decomposer.decompose("original") == ["original"]
    decision = evaluator.evaluate(
        original_query="original", subquestions=["missing"], evidence=[]
    )
    assert decision.sufficient is False
    assert decision.follow_up_queries == ["one", "two"]
