import hashlib
import json
import math
import uuid
from collections import OrderedDict
from contextlib import suppress
from dataclasses import asdict, dataclass, replace
from threading import RLock
from time import perf_counter
from typing import Protocol

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Course, Document, DocumentVersion
from app.evaluation.metrics import summarize
from app.generation.service import AnswerSentence, ChatResult, Citation, GroundedChatService
from app.retrieval.embeddings import EmbeddingProvider


@dataclass(frozen=True, slots=True)
class CacheContext:
    course_code: str
    corpus_fingerprint: str
    retrieval_config: str
    safety_policy: str
    model_config: str


@dataclass(frozen=True, slots=True)
class CacheLookup:
    result: ChatResult
    similarity: float


class CorpusFingerprintProvider(Protocol):
    def fingerprint(self, course_code: str) -> str: ...


class SqlAlchemyCorpusFingerprintProvider:
    def __init__(self, session: Session) -> None:
        self.session = session

    def fingerprint(self, course_code: str) -> str:
        values = self.session.execute(
            select(
                Document.id,
                Document.is_protected,
                DocumentVersion.id,
                DocumentVersion.content_sha256,
            )
            .join(DocumentVersion, DocumentVersion.document_id == Document.id)
            .join(Course, Document.course_id == Course.id)
            .where(Course.code == course_code, DocumentVersion.status == "completed")
            .order_by(Document.id, DocumentVersion.id)
        ).all()
        payload = [
            [str(document_id), protected, str(version_id), digest]
            for document_id, protected, version_id, digest in values
        ]
        return hashlib.sha256(
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


class RedisSemanticAnswerCache:
    def __init__(
        self,
        client: Redis,
        embedder: EmbeddingProvider,
        *,
        ttl_seconds: int,
        similarity_threshold: float,
        max_candidates: int,
    ) -> None:
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be positive")
        if not 0 <= similarity_threshold <= 1:
            raise ValueError("similarity_threshold must be between 0 and 1")
        if not 1 <= max_candidates <= 1000:
            raise ValueError("max_candidates must be between 1 and 1000")
        self.client = client
        self.embedder = embedder
        self.ttl_seconds = ttl_seconds
        self.similarity_threshold = similarity_threshold
        self.max_candidates = max_candidates
        self._query_vectors: OrderedDict[str, tuple[float, ...]] = OrderedDict()
        self._query_vectors_lock = RLock()

    def get(self, *, query: str, context: CacheContext) -> CacheLookup | None:
        keys = list(self.client.smembers(self._course_key(context.course_code)))[
            : self.max_candidates
        ]
        if not keys:
            return None
        payloads = self.client.mget(keys)
        query_vector = self._query_vector(query)
        best: tuple[float, dict] | None = None
        expired: list[bytes | str] = []
        for key, raw in zip(keys, payloads, strict=True):
            if raw is None:
                expired.append(key)
                continue
            entry = json.loads(raw)
            if not self._compatible(entry["context"], context):
                self.client.hincrby("illinois-chat:cache:metrics", "stale_rejections", 1)
                continue
            similarity = self._cosine(query_vector, entry["query_vector"])
            if similarity >= self.similarity_threshold and (
                best is None or similarity > best[0]
            ):
                best = (similarity, entry)
        if expired:
            self.client.srem(self._course_key(context.course_code), *expired)
        if best is None:
            return None
        return CacheLookup(result=self._deserialize(best[1]["result"]), similarity=best[0])

    def put(self, *, query: str, context: CacheContext, result: ChatResult) -> None:
        entry_id = uuid.uuid4().hex
        key = f"illinois-chat:cache:entry:{entry_id}"
        payload = {
            "normalized_query": query,
            "query_vector": self._query_vector(query),
            "context": asdict(context),
            "result": self._serialize(result),
        }
        pipeline = self.client.pipeline(transaction=True)
        pipeline.set(key, json.dumps(payload, separators=(",", ":")), ex=self.ttl_seconds)
        pipeline.sadd(self._course_key(context.course_code), key)
        pipeline.expire(self._course_key(context.course_code), self.ttl_seconds)
        pipeline.execute()

    @staticmethod
    def _course_key(course_code: str) -> str:
        digest = hashlib.sha256(course_code.encode("utf-8")).hexdigest()
        return f"illinois-chat:cache:course:{digest}"

    def _query_vector(self, query: str) -> list[float]:
        with self._query_vectors_lock:
            cached = self._query_vectors.get(query)
            if cached is not None:
                self._query_vectors.move_to_end(query)
                return list(cached)
            vector = tuple(self.embedder.embed_query(query))
            self._query_vectors[query] = vector
            if len(self._query_vectors) > 1024:
                self._query_vectors.popitem(last=False)
            return list(vector)

    @staticmethod
    def _compatible(stored: dict, current: CacheContext) -> bool:
        return stored == asdict(current)

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if len(left) != len(right):
            return 0.0
        numerator = sum(a * b for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if not left_norm or not right_norm:
            return 0.0
        return numerator / (left_norm * right_norm)

    @staticmethod
    def _serialize(result: ChatResult) -> dict:
        payload = asdict(result)
        payload["request_id"] = str(result.request_id)
        payload["retrieved_chunk_ids"] = [str(value) for value in result.retrieved_chunk_ids]
        for citation in payload["citations"]:
            for field in ("chunk_id", "document_id", "version_id"):
                citation[field] = str(citation[field])
        return payload

    @staticmethod
    def _deserialize(payload: dict) -> ChatResult:
        return ChatResult(
            request_id=uuid.UUID(payload["request_id"]),
            status=payload["status"],
            answer=payload["answer"],
            sentences=[AnswerSentence(**value) for value in payload["sentences"]],
            citations=[
                Citation(
                    **{
                        **value,
                        "chunk_id": uuid.UUID(value["chunk_id"]),
                        "document_id": uuid.UUID(value["document_id"]),
                        "version_id": uuid.UUID(value["version_id"]),
                    }
                )
                for value in payload["citations"]
            ],
            refusal_reason=payload["refusal_reason"],
            retrieved_chunk_ids=[uuid.UUID(value) for value in payload["retrieved_chunk_ids"]],
            model_name=payload["model_name"],
            latency_ms=payload["latency_ms"],
            safety_mode=payload.get("safety_mode", "standard"),
            hint_level=payload.get("hint_level"),
            protected_match_score=payload.get("protected_match_score"),
            retrieval_trace=payload.get("retrieval_trace"),
            cache_hit=payload.get("cache_hit", False),
            cache_similarity=payload.get("cache_similarity"),
        )


class CacheMetrics:
    METRICS_KEY = "illinois-chat:cache:metrics"
    LATENCY_KEY = "illinois-chat:cache:latencies"

    def __init__(self, client: Redis) -> None:
        self.client = client

    def record(self, outcome: str, latency_ms: float) -> None:
        pipeline = self.client.pipeline(transaction=False)
        pipeline.hincrby(self.METRICS_KEY, outcome, 1)
        pipeline.lpush(self.LATENCY_KEY, str(latency_ms))
        pipeline.ltrim(self.LATENCY_KEY, 0, 999)
        pipeline.execute()

    def snapshot(self) -> dict:
        raw = self.client.hgetall(self.METRICS_KEY)
        counts = {
            self._text(key): int(self._text(value)) for key, value in raw.items()
        }
        hits = counts.get("hits", 0)
        misses = counts.get("misses", 0)
        total = hits + misses
        latencies = [
            float(self._text(value))
            for value in self.client.lrange(self.LATENCY_KEY, 0, -1)
        ]
        stale_served = counts.get("stale_served", 0)
        return {
            **counts,
            "hit_rate": hits / total if total else 0.0,
            "stale_answer_rate": stale_served / hits if hits else 0.0,
            "latency_ms": summarize(latencies),
        }

    @staticmethod
    def _text(value: bytes | str) -> str:
        return value.decode() if isinstance(value, bytes) else value


class SemanticCachedChatService:
    def __init__(
        self,
        inner: GroundedChatService,
        cache: RedisSemanticAnswerCache,
        fingerprints: CorpusFingerprintProvider,
        metrics: CacheMetrics,
        *,
        retrieval_config: str,
        safety_policy: str,
        model_config: str,
    ) -> None:
        self.inner = inner
        self.cache = cache
        self.fingerprints = fingerprints
        self.metrics = metrics
        self.retrieval_config = retrieval_config
        self.safety_policy = safety_policy
        self.model_config = model_config

    def ask(self, *, course_code: str, query: str) -> ChatResult:
        started = perf_counter()
        normalized = " ".join(query.split())
        context = CacheContext(
            course_code=course_code.strip(),
            corpus_fingerprint=self.fingerprints.fingerprint(course_code.strip()),
            retrieval_config=self.retrieval_config,
            safety_policy=self.safety_policy,
            model_config=self.model_config,
        )
        try:
            cached = self.cache.get(query=normalized, context=context)
        except RedisError:
            return self.inner.ask(course_code=course_code, query=normalized)
        if cached is not None:
            latency_ms = max(0, round((perf_counter() - started) * 1000))
            with suppress(RedisError):
                self.metrics.record("hits", latency_ms)
            return replace(
                cached.result,
                request_id=uuid.uuid4(),
                latency_ms=latency_ms,
                cache_hit=True,
                cache_similarity=cached.similarity,
            )
        result = self.inner.ask(course_code=course_code, query=normalized)
        latency_ms = max(0, round((perf_counter() - started) * 1000))
        with suppress(RedisError):
            self.metrics.record("misses", latency_ms)
        if result.status == "answered" and result.safety_mode == "standard":
            with suppress(RedisError):
                self.cache.put(query=normalized, context=context, result=result)
        return result
