import uuid
from dataclasses import dataclass, replace

from app.caching.semantic import (
    CacheContext,
    CacheMetrics,
    RedisSemanticAnswerCache,
    SemanticCachedChatService,
)
from app.generation.service import AnswerSentence, ChatResult, Citation


class FakePipeline:
    def __init__(self, redis):
        self.redis = redis
        self.operations = []

    def __getattr__(self, name):
        def queue(*args, **kwargs):
            self.operations.append((name, args, kwargs))
            return self

        return queue

    def execute(self):
        return [
            getattr(self.redis, name)(*args, **kwargs)
            for name, args, kwargs in self.operations
        ]


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.sets = {}
        self.hashes = {}
        self.lists = {}

    def pipeline(self, **_kwargs):
        return FakePipeline(self)

    def set(self, key, value, **_kwargs):
        self.values[key] = value

    def sadd(self, key, *values):
        self.sets.setdefault(key, set()).update(values)

    def smembers(self, key):
        return self.sets.get(key, set())

    def srem(self, key, *values):
        self.sets.setdefault(key, set()).difference_update(values)

    def mget(self, keys):
        return [self.values.get(key) for key in keys]

    def expire(self, *_args):
        return True

    def hincrby(self, key, field, amount):
        current = self.hashes.setdefault(key, {})
        current[field] = current.get(field, 0) + amount

    def hgetall(self, key):
        return self.hashes.get(key, {})

    def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)

    def ltrim(self, key, start, end):
        self.lists[key] = self.lists.get(key, [])[start : end + 1]

    def lrange(self, key, start, end):
        values = self.lists.get(key, [])
        return values[start:] if end == -1 else values[start : end + 1]


class FakeEmbedder:
    model_name = "fake"
    dimension = 2

    def embed_query(self, text):
        return [1.0, 0.0] if "vector" in text.lower() else [0.0, 1.0]


class CountingEmbedder(FakeEmbedder):
    def __init__(self):
        self.calls = 0

    def embed_query(self, text):
        self.calls += 1
        return super().embed_query(text)


def answer() -> ChatResult:
    return ChatResult(
        request_id=uuid.uuid4(),
        status="answered",
        answer="Vector search uses embeddings.",
        sentences=[AnswerSentence("Vector search uses embeddings.", [1])],
        citations=[
            Citation(
                citation_id=1,
                chunk_id=uuid.UUID(int=1),
                document_id=uuid.UUID(int=2),
                version_id=uuid.UUID(int=3),
                title="Notes",
                source_name="notes.md",
                page_number=None,
                section_path="Vector",
                evidence="Vector search uses embeddings.",
                score=0.9,
            )
        ],
        refusal_reason=None,
        retrieved_chunk_ids=[uuid.UUID(int=1)],
        model_name="model",
        latency_ms=50,
    )


def context(corpus="v1") -> CacheContext:
    return CacheContext("CS", corpus, "retrieval", "safety", "model")


def test_semantic_cache_hits_similar_query_and_rehydrates_result() -> None:
    cache = RedisSemanticAnswerCache(
        FakeRedis(), FakeEmbedder(), ttl_seconds=60, similarity_threshold=0.9, max_candidates=10
    )
    cache.put(query="vector retrieval", context=context(), result=answer())

    hit = cache.get(query="explain vector search", context=context())

    assert hit is not None
    assert hit.similarity == 1.0
    assert hit.result.citations[0].chunk_id == uuid.UUID(int=1)
    assert hit.result.sentences[0].citation_ids == [1]


def test_cache_rejects_stale_corpus_and_records_rejection() -> None:
    redis = FakeRedis()
    cache = RedisSemanticAnswerCache(
        redis, FakeEmbedder(), ttl_seconds=60, similarity_threshold=0.9, max_candidates=10
    )
    cache.put(query="vector retrieval", context=context("v1"), result=answer())

    assert cache.get(query="vector retrieval", context=context("v2")) is None
    assert redis.hashes[CacheMetrics.METRICS_KEY]["stale_rejections"] == 1


def test_exact_query_embedding_is_cached_in_process() -> None:
    embedder = CountingEmbedder()
    cache = RedisSemanticAnswerCache(
        FakeRedis(), embedder, ttl_seconds=60, similarity_threshold=0.9, max_candidates=10
    )
    cache.put(query="vector retrieval", context=context(), result=answer())

    cache.get(query="vector retrieval", context=context())
    cache.get(query="vector retrieval", context=context())

    assert embedder.calls == 1


@dataclass
class StaticFingerprints:
    value: str = "v1"

    def fingerprint(self, _course_code):
        return self.value


@dataclass
class CountingChat:
    result: ChatResult
    calls: int = 0

    def ask(self, **_kwargs):
        self.calls += 1
        return self.result


def test_cached_chat_skips_inner_service_and_exposes_metrics() -> None:
    redis = FakeRedis()
    cache = RedisSemanticAnswerCache(
        redis, FakeEmbedder(), ttl_seconds=60, similarity_threshold=0.9, max_candidates=10
    )
    inner = CountingChat(answer())
    metrics = CacheMetrics(redis)
    service = SemanticCachedChatService(
        inner,
        cache,
        StaticFingerprints(),
        metrics,
        retrieval_config="retrieval",
        safety_policy="safety",
        model_config="model",
    )

    first = service.ask(course_code="CS", query="vector retrieval")
    second = service.ask(course_code="CS", query="explain vector search")
    snapshot = metrics.snapshot()

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.request_id != first.request_id
    assert inner.calls == 1
    assert snapshot["hits"] == 1
    assert snapshot["misses"] == 1
    assert snapshot["hit_rate"] == 0.5
    assert snapshot["stale_answer_rate"] == 0.0


def test_protected_hint_is_not_cached() -> None:
    redis = FakeRedis()
    protected = replace(
        answer(),
        status="homework_hint",
        safety_mode="protected_assignment",
    )
    inner = CountingChat(protected)
    service = SemanticCachedChatService(
        inner,
        RedisSemanticAnswerCache(
            redis,
            FakeEmbedder(),
            ttl_seconds=60,
            similarity_threshold=0.9,
            max_candidates=10,
        ),
        StaticFingerprints(),
        CacheMetrics(redis),
        retrieval_config="retrieval",
        safety_policy="safety",
        model_config="model",
    )

    service.ask(course_code="CS", query="vector assignment")
    service.ask(course_code="CS", query="vector assignment")

    assert inner.calls == 2
