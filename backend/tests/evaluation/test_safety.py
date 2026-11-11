from dataclasses import dataclass
from pathlib import Path

from app.evaluation.safety import (
    SafetyEvaluator,
    contains_solution_leakage,
    load_safety_dataset,
)


@dataclass
class Result:
    status: str
    answer: str | None


class DeterministicSafetyChat:
    def ask(self, *, course_code, query):
        del course_code
        protected = any(
            marker in query.lower()
            for marker in ("homework 1", "assignment one", "hw1", "solution", "protected")
        )
        return Result(
            "homework_hint" if protected else "answered",
            "Review the relevant concept." if protected else "Explanation",
        )


def test_committed_safety_dataset_and_evaluator() -> None:
    path = Path("data/evaluation/m3-safety-v1.jsonl")
    cases = load_safety_dataset(path)
    summary = SafetyEvaluator(DeterministicSafetyChat()).run(path)

    assert len(cases) == 14
    assert len({case.id for case in cases}) == 14
    assert summary.protected_cases == 9
    assert summary.detection_recall == 1.0
    assert summary.protection_bypass_rate == 0.0
    assert summary.assignment_leakage_rate == 0.0
    assert summary.false_positive_rate == 0.0
    assert summary.behavior_compliance_rate == 1.0
    assert summary.review_status_counts == {"human_reviewed": 14}


def test_solution_leakage_markers_are_fail_closed_for_code() -> None:
    assert contains_solution_leakage("```python\ndef reciprocal_rank_fusion(a, b):\n    pass")
    assert not contains_solution_leakage("Review how rank contributions are accumulated.")
