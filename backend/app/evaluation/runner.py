from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from pydantic import BaseModel, ConfigDict, Field

from app.evaluation.metrics import ndcg_at_k, summarize
from app.retrieval.service import RetrievalService


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    course_code: str = Field(min_length=1)
    query: str = Field(min_length=1)
    category: str
    answerable: bool
    relevant_sections: dict[str, int]
    review_status: str


@dataclass(frozen=True, slots=True)
class EvaluationSummary:
    dataset: str
    total_cases: int
    scored_cases: int
    recall_at_5: float
    ndcg_at_10: float
    latency_ms: dict[str, float]
    review_status_counts: dict[str, int]


def load_dataset(path: Path) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            case = EvaluationCase.model_validate_json(line)
            if case.id in seen:
                raise ValueError(f"Duplicate evaluation id {case.id} on line {line_number}")
            seen.add(case.id)
            cases.append(case)
    if not 30 <= len(cases) <= 50:
        raise ValueError("The initial evaluation dataset must contain 30-50 cases")
    return cases


class RetrievalEvaluator:
    def __init__(self, retrieval: RetrievalService) -> None:
        self.retrieval = retrieval

    def run(self, path: Path, repetitions: int = 1) -> EvaluationSummary:
        if repetitions < 1:
            raise ValueError("repetitions must be positive")
        cases = load_dataset(path)
        recalls: list[float] = []
        ndcgs: list[float] = []
        latencies: list[float] = []
        status_counts: dict[str, int] = {}
        for case in cases:
            status_counts[case.review_status] = status_counts.get(case.review_status, 0) + 1
            if not case.answerable:
                continue
            results = []
            for _ in range(repetitions):
                started = perf_counter()
                current = self.retrieval.search(
                    course_code=case.course_code, query=case.query, top_k=10
                )
                latencies.append((perf_counter() - started) * 1000)
                if not results:
                    results = current
            seen_sections: set[str] = set()
            grades: list[int] = []
            for result in results:
                section = result.section_path or ""
                grade = case.relevant_sections.get(section, 0)
                if section in seen_sections:
                    grade = 0
                seen_sections.add(section)
                grades.append(grade)
            all_grades = list(case.relevant_sections.values())
            retrieved_sections = {
                result.section_path
                for result in results[:5]
                if result.section_path in case.relevant_sections
            }
            recalls.append(len(retrieved_sections) / len(case.relevant_sections))
            ndcgs.append(ndcg_at_k(grades, 10, all_grades))
        return EvaluationSummary(
            dataset=path.name,
            total_cases=len(cases),
            scored_cases=len(recalls),
            recall_at_5=sum(recalls) / len(recalls) if recalls else 0.0,
            ndcg_at_10=sum(ndcgs) / len(ndcgs) if ndcgs else 0.0,
            latency_ms=summarize(latencies),
            review_status_counts=status_counts,
        )
