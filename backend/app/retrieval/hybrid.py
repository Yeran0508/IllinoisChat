from dataclasses import replace
from math import exp

from app.retrieval.lexical import ChunkLexicalIndex
from app.retrieval.reranking import Reranker
from app.retrieval.service import RetrievalResult, RetrievalService


class HybridRetrievalService:
    def __init__(
        self,
        *,
        vector: RetrievalService,
        lexical: ChunkLexicalIndex,
        reranker: Reranker,
        candidate_k: int = 20,
        rrf_rank_constant: int = 60,
    ) -> None:
        if candidate_k < 1 or candidate_k > 100:
            raise ValueError("candidate_k must be between 1 and 100")
        if rrf_rank_constant < 1:
            raise ValueError("rrf_rank_constant must be positive")
        self.vector = vector
        self.lexical = lexical
        self.reranker = reranker
        self.candidate_k = candidate_k
        self.rrf_rank_constant = rrf_rank_constant

    def search(self, *, course_code: str, query: str, top_k: int) -> list[RetrievalResult]:
        if top_k < 1 or top_k > 50:
            raise ValueError("top_k must be between 1 and 50")
        vector_results = self.vector.search(
            course_code=course_code, query=query, top_k=self.candidate_k
        )
        lexical_results = self.lexical.search(
            course_code=course_code, query=query, top_k=self.candidate_k
        )
        fused = self._rrf(vector_results, lexical_results)
        if not fused:
            return []
        scores = self.reranker.score(query, [result.content for result in fused])
        if len(scores) != len(fused):
            raise ValueError("Reranker returned an unexpected score count")
        reranked = [
            replace(
                result,
                score=self._sigmoid(score),
                retrieval_metadata={
                    **result.retrieval_metadata,
                    "reranker_logit": score,
                    "reranker_model": self.reranker.model_name,
                },
            )
            for result, score in zip(fused, scores, strict=True)
        ]
        reranked.sort(key=lambda value: value.score, reverse=True)
        return reranked[:top_k]

    def _rrf(
        self,
        vector_results: list[RetrievalResult],
        lexical_results: list[RetrievalResult],
    ) -> list[RetrievalResult]:
        by_id: dict = {}
        scores: dict = {}
        metadata: dict = {}
        for source, results in (("vector", vector_results), ("bm25", lexical_results)):
            for rank, result in enumerate(results, start=1):
                by_id.setdefault(result.chunk_id, result)
                scores[result.chunk_id] = scores.get(result.chunk_id, 0.0) + (
                    1.0 / (self.rrf_rank_constant + rank)
                )
                metadata.setdefault(result.chunk_id, {}).update(result.retrieval_metadata)
                metadata[result.chunk_id][f"{source}_rank"] = rank
        fused = [
            replace(
                result,
                score=scores[chunk_id],
                retrieval_metadata={
                    **metadata[chunk_id],
                    "rrf_score": scores[chunk_id],
                },
            )
            for chunk_id, result in by_id.items()
        ]
        fused.sort(key=lambda value: value.score, reverse=True)
        return fused[: self.candidate_k]

    @staticmethod
    def _sigmoid(value: float) -> float:
        if value >= 0:
            return 1.0 / (1.0 + exp(-value))
        exponent = exp(value)
        return exponent / (1.0 + exponent)
