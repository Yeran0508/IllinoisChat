import math
import statistics
from collections.abc import Sequence


def recall_at_k(relevance: Sequence[int], k: int, total_relevant: int | None = None) -> float:
    total_relevant = total_relevant or sum(1 for value in relevance if value > 0)
    if total_relevant == 0:
        return 0.0
    return sum(1 for value in relevance[:k] if value > 0) / total_relevant


def ndcg_at_k(
    relevance: Sequence[int], k: int, ideal_relevance: Sequence[int] | None = None
) -> float:
    actual = _dcg(relevance[:k])
    ideal_values = ideal_relevance if ideal_relevance is not None else relevance
    ideal = _dcg(sorted(ideal_values, reverse=True)[:k])
    return actual / ideal if ideal else 0.0


def percentile(values: Sequence[float], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * probability
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def summarize(values: Sequence[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "p50": 0.0, "p95": 0.0}
    return {
        "mean": statistics.fmean(values),
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
    }


def citation_precision(supported: Sequence[bool]) -> float:
    if not supported:
        return 0.0
    return sum(supported) / len(supported)


def unsupported_claim_rate(supported: Sequence[bool]) -> float:
    if not supported:
        return 0.0
    return 1.0 - citation_precision(supported)


def assignment_leakage_rate(leaked: Sequence[bool]) -> float:
    if not leaked:
        return 0.0
    return sum(leaked) / len(leaked)


def _dcg(relevance: Sequence[int]) -> float:
    return sum((2**grade - 1) / math.log2(rank + 2) for rank, grade in enumerate(relevance))
