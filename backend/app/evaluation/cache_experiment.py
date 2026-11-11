import argparse
import json
import platform
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from redis import Redis

from app.caching.semantic import (
    CacheMetrics,
    RedisSemanticAnswerCache,
    SemanticCachedChatService,
)
from app.config import get_settings
from app.evaluation.metrics import summarize
from app.generation.service import AnswerSentence, ChatResult
from app.retrieval.embeddings import FastEmbedBgeProvider


@dataclass(slots=True)
class StaticFingerprint:
    value: str

    def fingerprint(self, _course_code: str) -> str:
        return self.value


class SimulatedUpstreamChat:
    def __init__(self, delay_seconds: float) -> None:
        self.delay_seconds = delay_seconds
        self.calls = 0
        self._lock = threading.Lock()

    def ask(self, **_kwargs) -> ChatResult:
        time.sleep(self.delay_seconds)
        with self._lock:
            self.calls += 1
        return ChatResult(
            request_id=uuid.uuid4(),
            status="answered",
            answer="Synthetic grounded answer.",
            sentences=[AnswerSentence("Synthetic grounded answer.", [1])],
            citations=[],
            refusal_reason=None,
            retrieved_chunk_ids=[],
            model_name="simulated-upstream",
            latency_ms=round(self.delay_seconds * 1000),
        )


def _timed(service, query: str) -> tuple[float, bool]:
    started = perf_counter()
    result = service.ask(course_code="CS-CACHE-EXPERIMENT", query=query)
    return (perf_counter() - started) * 1000, result.cache_hit


def run(output: Path, concurrent_requests: int) -> dict:
    settings = get_settings()
    client = Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        decode_responses=False,
    )
    keys = list(client.scan_iter("illinois-chat:cache:*"))
    if keys:
        client.delete(*keys)
    embedder = FastEmbedBgeProvider(
        model_name=settings.embedding_model,
        cache_dir=str(settings.embedding_cache_path),
    )
    fingerprints = StaticFingerprint("corpus-v1")
    upstream = SimulatedUpstreamChat(delay_seconds=0.05)
    metrics = CacheMetrics(client)
    service = SemanticCachedChatService(
        upstream,
        RedisSemanticAnswerCache(
            client,
            embedder,
            ttl_seconds=settings.semantic_cache_ttl_seconds,
            similarity_threshold=settings.semantic_cache_similarity_threshold,
            max_candidates=settings.semantic_cache_max_candidates,
        ),
        fingerprints,
        metrics,
        retrieval_config="m5-experiment-retrieval-v1",
        safety_policy="m5-experiment-safety-v1",
        model_config="simulated-upstream-v1",
    )
    query = "How does reciprocal rank fusion combine ranked lists?"
    cold_latency, cold_hit = _timed(service, query)
    warm_latencies = [_timed(service, query)[0] for _ in range(20)]

    started = perf_counter()
    with ThreadPoolExecutor(max_workers=10) as executor:
        concurrent = list(
            executor.map(
                lambda _index: _timed(service, query),
                range(concurrent_requests),
            )
        )
    concurrent_wall_ms = (perf_counter() - started) * 1000

    fingerprints.value = "corpus-v2"
    stale_latency, stale_hit = _timed(service, query)
    snapshot = metrics.snapshot()
    total_requests = 1 + len(warm_latencies) + concurrent_requests + 1
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "redis": "7.4.3-alpine",
        "embedding_model": settings.embedding_model,
        "similarity_threshold": settings.semantic_cache_similarity_threshold,
        "ttl_seconds": settings.semantic_cache_ttl_seconds,
        "max_candidates": settings.semantic_cache_max_candidates,
        "simulated_upstream_delay_ms": 50,
        "requests": total_requests,
        "concurrent_requests": concurrent_requests,
        "cold": {"latency_ms": cold_latency, "cache_hit": cold_hit},
        "warm": {"latency_ms": summarize(warm_latencies), "requests": 20},
        "concurrent_warm": {
            "latency_ms": summarize([value[0] for value in concurrent]),
            "wall_ms": concurrent_wall_ms,
            "requests": concurrent_requests,
            "workers": 10,
        },
        "after_corpus_change": {
            "latency_ms": stale_latency,
            "cache_hit": stale_hit,
        },
        "metrics": snapshot,
        "upstream_calls": upstream.calls,
        "upstream_calls_avoided": total_requests - upstream.calls,
        "limitations": [
            "The upstream delay is simulated and is not a real LLM latency measurement.",
            "The workload uses one pre-warmed query and does not measure cache stampede "
            "on cold keys.",
            "The corpus fingerprint is controlled directly to isolate invalidation behavior.",
            "Dollar cost is not reported; avoided upstream calls are the cost proxy.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--concurrent-requests", type=int, default=100)
    args = parser.parse_args()
    print(json.dumps(run(args.output, args.concurrent_requests), indent=2))


if __name__ == "__main__":
    main()
