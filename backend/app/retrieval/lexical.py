import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.retrieval.service import RetrievalResult


class LexicalIndexError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class IndexedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    version_id: uuid.UUID
    course_code: str
    title: str
    source_name: str
    content: str
    page_number: int | None
    section_path: str | None


class ChunkLexicalIndex(Protocol):
    def replace_version(self, version_id: uuid.UUID, chunks: Sequence[IndexedChunk]) -> None: ...

    def delete_document(self, document_id: uuid.UUID) -> None: ...

    def delete_version(self, version_id: uuid.UUID) -> None: ...

    def search(self, *, course_code: str, query: str, top_k: int) -> list[RetrievalResult]: ...


class NoOpChunkLexicalIndex:
    def replace_version(self, version_id: uuid.UUID, chunks: Sequence[IndexedChunk]) -> None:
        del version_id, chunks

    def delete_document(self, document_id: uuid.UUID) -> None:
        del document_id

    def delete_version(self, version_id: uuid.UUID) -> None:
        del version_id

    def search(self, *, course_code: str, query: str, top_k: int) -> list[RetrievalResult]:
        del course_code, query, top_k
        return []


class OpenSearchBM25Index:
    def __init__(
        self,
        *,
        base_url: str,
        index_name: str,
        timeout_seconds: float,
        client: httpx.Client | None = None,
    ) -> None:
        self.index_name = index_name
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"), timeout=timeout_seconds
        )

    def ensure_index(self) -> None:
        response = self._client.head(f"/{self.index_name}")
        if response.status_code == 200:
            return
        if response.status_code != 404:
            self._raise(response, "check index")
        response = self._client.put(
            f"/{self.index_name}",
            json={
                "mappings": {
                    "dynamic": "strict",
                    "properties": {
                        "chunk_id": {"type": "keyword"},
                        "document_id": {"type": "keyword"},
                        "version_id": {"type": "keyword"},
                        "course_code": {"type": "keyword"},
                        "title": {"type": "text"},
                        "source_name": {"type": "keyword"},
                        "content": {"type": "text"},
                        "page_number": {"type": "integer"},
                        "section_path": {"type": "text"},
                    },
                }
            },
        )
        if response.status_code not in {200, 201}:
            self._raise(response, "create index")

    def replace_version(self, version_id: uuid.UUID, chunks: Sequence[IndexedChunk]) -> None:
        self.ensure_index()
        self._delete_by_term("version_id", str(version_id))
        if not chunks:
            return
        lines: list[str] = []
        for chunk in chunks:
            lines.append(
                json.dumps({"index": {"_index": self.index_name, "_id": str(chunk.chunk_id)}})
            )
            lines.append(json.dumps(self._source(chunk)))
        response = self._client.post(
            "/_bulk?refresh=wait_for",
            content="\n".join(lines) + "\n",
            headers={"Content-Type": "application/x-ndjson"},
        )
        if response.status_code != 200:
            self._raise(response, "bulk index chunks")
        if response.json().get("errors"):
            raise LexicalIndexError("OpenSearch bulk indexing reported item failures")

    def delete_document(self, document_id: uuid.UUID) -> None:
        self.ensure_index()
        self._delete_by_term("document_id", str(document_id))

    def delete_version(self, version_id: uuid.UUID) -> None:
        self.ensure_index()
        self._delete_by_term("version_id", str(version_id))

    def search(self, *, course_code: str, query: str, top_k: int) -> list[RetrievalResult]:
        query = query.strip()
        if not query:
            raise ValueError("Query must not be blank")
        if top_k < 1 or top_k > 100:
            raise ValueError("top_k must be between 1 and 100")
        self.ensure_index()
        response = self._client.post(
            f"/{self.index_name}/_search",
            json={
                "size": top_k,
                "query": {
                    "bool": {
                        "filter": [{"term": {"course_code": course_code}}],
                        "must": [
                            {
                                "multi_match": {
                                    "query": query,
                                    "fields": ["content", "title^2", "section_path^1.5"],
                                }
                            }
                        ],
                    }
                },
            },
        )
        if response.status_code != 200:
            self._raise(response, "search")
        return [self._result(hit) for hit in response.json()["hits"]["hits"]]

    def _delete_by_term(self, field: str, value: str) -> None:
        response = self._client.post(
            f"/{self.index_name}/_delete_by_query?refresh=true&conflicts=proceed",
            json={"query": {"term": {field: value}}},
        )
        if response.status_code != 200:
            self._raise(response, "delete stale chunks")

    @staticmethod
    def _source(chunk: IndexedChunk) -> dict:
        return {
            "chunk_id": str(chunk.chunk_id),
            "document_id": str(chunk.document_id),
            "version_id": str(chunk.version_id),
            "course_code": chunk.course_code,
            "title": chunk.title,
            "source_name": chunk.source_name,
            "content": chunk.content,
            "page_number": chunk.page_number,
            "section_path": chunk.section_path,
        }

    @staticmethod
    def _result(hit: dict) -> RetrievalResult:
        source = hit["_source"]
        score = float(hit.get("_score") or 0.0)
        return RetrievalResult(
            chunk_id=uuid.UUID(source["chunk_id"]),
            document_id=uuid.UUID(source["document_id"]),
            version_id=uuid.UUID(source["version_id"]),
            title=source["title"],
            source_name=source["source_name"],
            content=source["content"],
            page_number=source.get("page_number"),
            section_path=source.get("section_path"),
            score=score,
            retrieval_metadata={"bm25_score": score},
        )

    @staticmethod
    def _raise(response: httpx.Response, operation: str) -> None:
        raise LexicalIndexError(
            f"OpenSearch failed to {operation}: HTTP {response.status_code}: {response.text[:500]}"
        )
