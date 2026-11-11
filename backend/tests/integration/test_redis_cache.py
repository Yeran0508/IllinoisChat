import os
import uuid

import pytest
from app.caching.semantic import CacheContext, CacheMetrics, RedisSemanticAnswerCache
from app.generation.service import AnswerSentence, ChatResult
from redis import Redis

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_REDIS_TESTS") != "1",
        reason="requires Redis",
    ),
]


class FakeEmbedder:
    model_name = "fake"
    dimension = 2

    def embed_query(self, _text):
        return [1.0, 0.0]


def answer() -> ChatResult:
    return ChatResult(
        request_id=uuid.uuid4(),
        status="answered",
        answer="Cached answer",
        sentences=[AnswerSentence("Cached answer", [1])],
        citations=[],
        refusal_reason=None,
        retrieved_chunk_ids=[],
        model_name="test",
        latency_ms=10,
    )


def test_real_redis_semantic_hit_and_stale_rejection() -> None:
    client = Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        decode_responses=False,
    )
    keys = list(client.scan_iter("illinois-chat:cache:*"))
    if keys:
        client.delete(*keys)
    cache = RedisSemanticAnswerCache(
        client,
        FakeEmbedder(),
        ttl_seconds=60,
        similarity_threshold=0.9,
        max_candidates=10,
    )
    v1 = CacheContext("CS-REDIS", "v1", "retrieval", "safety", "model")
    v2 = CacheContext("CS-REDIS", "v2", "retrieval", "safety", "model")
    expected: ChatResult = answer()

    cache.put(query="vector retrieval", context=v1, result=expected)

    hit = cache.get(query="explain vector retrieval", context=v1)
    stale = cache.get(query="vector retrieval", context=v2)

    assert hit is not None
    assert hit.result.answer == expected.answer
    assert stale is None
    metrics = CacheMetrics(client).snapshot()
    assert metrics["stale_rejections"] == 1
