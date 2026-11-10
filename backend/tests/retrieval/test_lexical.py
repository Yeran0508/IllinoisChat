import json
import uuid

import httpx
import pytest
from app.retrieval.lexical import IndexedChunk, LexicalIndexError, OpenSearchBM25Index


def test_opensearch_creates_index_bulk_replaces_and_searches() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "HEAD":
            return httpx.Response(404)
        if request.method == "PUT":
            return httpx.Response(200, json={"acknowledged": True})
        if "_delete_by_query" in request.url.path:
            return httpx.Response(200, json={"deleted": 0})
        if request.url.path == "/_bulk":
            return httpx.Response(200, json={"errors": False})
        return httpx.Response(
            200,
            json={
                "hits": {
                    "hits": [
                        {
                            "_score": 3.2,
                            "_source": {
                                "chunk_id": str(uuid.UUID(int=1)),
                                "document_id": str(uuid.UUID(int=2)),
                                "version_id": str(uuid.UUID(int=3)),
                                "title": "HNSW",
                                "source_name": "notes.md",
                                "content": "graph index",
                                "page_number": 1,
                                "section_path": "Indexes",
                            },
                        }
                    ]
                }
            },
        )

    client = httpx.Client(base_url="http://search.test", transport=httpx.MockTransport(handler))
    index = OpenSearchBM25Index(
        base_url="http://unused", index_name="chunks", timeout_seconds=1, client=client
    )
    chunk = IndexedChunk(
        uuid.UUID(int=1),
        uuid.UUID(int=2),
        uuid.UUID(int=3),
        "CS",
        "HNSW",
        "notes.md",
        "graph index",
        1,
        "Indexes",
    )

    index.replace_version(chunk.version_id, [chunk])
    results = index.search(course_code="CS", query="graph", top_k=5)

    assert results[0].score == 3.2
    bulk = next(request for request in requests if request.url.path == "/_bulk")
    lines = bulk.content.decode().splitlines()
    assert json.loads(lines[1])["course_code"] == "CS"
    search = requests[-1]
    assert json.loads(search.content)["query"]["bool"]["filter"] == [
        {"term": {"course_code": "CS"}}
    ]


def test_opensearch_reports_bulk_item_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(200)
        if "_delete_by_query" in request.url.path:
            return httpx.Response(200)
        return httpx.Response(200, json={"errors": True})

    index = OpenSearchBM25Index(
        base_url="http://search.test",
        index_name="chunks",
        timeout_seconds=1,
        client=httpx.Client(base_url="http://search.test", transport=httpx.MockTransport(handler)),
    )
    chunk = IndexedChunk(
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        "CS",
        "Title",
        "notes.md",
        "text",
        None,
        None,
    )
    with pytest.raises(LexicalIndexError, match="item failures"):
        index.replace_version(chunk.version_id, [chunk])
