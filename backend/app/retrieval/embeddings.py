from collections.abc import Sequence
from typing import Protocol


class EmbeddingProvider(Protocol):
    model_name: str
    dimension: int

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedBgeProvider:
    dimension = 384
    query_instruction = "Represent this sentence for searching relevant passages: "

    def __init__(self, model_name: str, cache_dir: str) -> None:
        from fastembed import TextEmbedding

        self.model_name = model_name
        self._model = TextEmbedding(model_name=model_name, cache_dir=cache_dir)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.embed(list(texts))]

    def embed_query(self, text: str) -> list[float]:
        value = f"{self.query_instruction}{text.strip()}"
        return next(self._model.embed([value])).tolist()
