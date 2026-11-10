import os
import uuid
from contextlib import suppress

import httpx
import pytest
from app.retrieval.lexical import IndexedChunk, OpenSearchBM25Index

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_OPENSEARCH_TESTS") != "1",
        reason="requires OpenSearch",
    ),
]


def chunk(
    value: int,
    course_code: str,
    content: str,
    section_path: str = "Information Retrieval > BM25",
) -> IndexedChunk:
    return IndexedChunk(
        chunk_id=uuid.UUID(int=value),
        document_id=uuid.UUID(int=100 + value),
        version_id=uuid.UUID(int=200 + value),
        course_code=course_code,
        title="Retrieval Notes",
        source_name="notes.md",
        content=content,
        page_number=None,
        section_path=section_path,
    )


def test_real_opensearch_bm25_course_filter_replace_and_delete() -> None:
    host = os.getenv("OPENSEARCH_HOST", "opensearch")
    port = int(os.getenv("OPENSEARCH_PORT", "9200"))
    index_name = f"illinois-chat-test-{uuid.uuid4().hex}"
    client = httpx.Client(base_url=f"http://{host}:{port}", timeout=20)
    index = OpenSearchBM25Index(
        base_url=f"http://{host}:{port}",
        index_name=index_name,
        timeout_seconds=20,
        client=client,
    )
    first = chunk(1, "CS-A", "BM25 uses inverse document frequency")
    second = chunk(
        2,
        "CS-A",
        "Dense vectors capture semantic similarity",
        "Information Retrieval > Dense Retrieval",
    )
    other_course = chunk(3, "CS-B", "BM25 BM25 inverse document frequency")
    try:
        index.replace_version(first.version_id, [first])
        index.replace_version(second.version_id, [second])
        index.replace_version(other_course.version_id, [other_course])

        results = index.search(course_code="CS-A", query="BM25 inverse document frequency", top_k=5)
        assert results[0].chunk_id == first.chunk_id
        assert other_course.chunk_id not in {value.chunk_id for value in results}

        replacement = chunk(4, "CS-A", "term frequency saturation parameter")
        replacement = IndexedChunk(
            replacement.chunk_id,
            replacement.document_id,
            first.version_id,
            replacement.course_code,
            replacement.title,
            replacement.source_name,
            replacement.content,
            replacement.page_number,
            replacement.section_path,
        )
        index.replace_version(first.version_id, [replacement])
        assert not index.search(course_code="CS-A", query="inverse", top_k=5)

        index.delete_document(replacement.document_id)
        assert not index.search(course_code="CS-A", query="saturation parameter", top_k=5)
    finally:
        with suppress(httpx.HTTPError):
            client.delete(f"/{index_name}")
