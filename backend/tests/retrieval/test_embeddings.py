import sys
from types import SimpleNamespace

from app.retrieval.embeddings import FastEmbedBgeProvider


class FakeVector(list[float]):
    def tolist(self) -> list[float]:
        return list(self)


class FakeTextEmbedding:
    def __init__(self, *, model_name: str, cache_dir: str) -> None:
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.received: list[str] = []

    def embed(self, texts: list[str]):
        self.received.extend(texts)
        for text in texts:
            yield FakeVector([float(len(text)), 1.0])


def test_fastembed_provider_separates_document_and_query_encoding(monkeypatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "fastembed",
        SimpleNamespace(TextEmbedding=FakeTextEmbedding),
    )
    provider = FastEmbedBgeProvider("test-model", "/tmp/models")

    documents = provider.embed_documents(["course notes"])
    query = provider.embed_query("vector search")

    assert documents == [[12.0, 1.0]]
    assert query[0] > documents[0][0]
    assert provider._model.received[-1].endswith("vector search")
    assert provider.model_name == "test-model"
