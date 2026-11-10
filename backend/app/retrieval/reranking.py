from collections.abc import Sequence
from typing import Protocol


class Reranker(Protocol):
    model_name: str

    def score(self, query: str, documents: Sequence[str]) -> list[float]: ...


class FastEmbedCrossEncoderReranker:
    def __init__(self, model_name: str, cache_dir: str) -> None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self.model_name = model_name
        self._model = TextCrossEncoder(model_name=model_name, cache_dir=cache_dir)

    def score(self, query: str, documents: Sequence[str]) -> list[float]:
        return [float(value) for value in self._model.rerank(query, list(documents))]
