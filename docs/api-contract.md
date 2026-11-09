# Illinois Chat API Contract

This document records only endpoints whose contract has been introduced in the implementation.

## `GET /api/v1/health`

Confirms that the API process and HTTP routing are available. It is a liveness endpoint and does not claim that PostgreSQL, OpenSearch, Redis, or external model providers are ready.

### Response: `200 OK`

```json
{
  "status": "ok",
  "service": "Illinois Chat API",
  "version": "0.1.0",
  "environment": "development"
}
```

## `POST /api/v1/documents`

Registers a PDF, UTF-8 Markdown, or UTF-8 plain-text source as multipart form data. Required fields are `course_code`, `course_name`, `title`, and `file`. A new content hash returns `201`; an existing version of the same logical source returns `200` with `reused: true`.

```json
{
  "document_id": "00000000-0000-0000-0000-000000000001",
  "version_id": "00000000-0000-0000-0000-000000000002",
  "status": "pending",
  "reused": false
}
```

## `POST /api/v1/documents/{document_id}/ingest`

Schedules parsing, chunking, and embedding for the requested `version_id`, or the latest version when omitted. Returns `202 Accepted`. The local implementation uses a FastAPI background task; a durable worker queue is required before production deployment.

## `GET /api/v1/documents/{document_id}`

Returns logical document metadata and all versions, including processing status, content hash, embedding model, timestamps, and a bounded failure message.

## `DELETE /api/v1/documents/{document_id}`

Deletes the document, versions, chunks, and locally stored source files. Returns `204 No Content`.

## `POST /api/v1/retrieval/search`

Embeds the query and retrieves completed chunks for one course using pgvector cosine distance.

```json
{
  "course_code": "CS411",
  "query": "How does an HNSW index trade recall for latency?",
  "top_k": 5
}
```

The response returns chunk, document, and version IDs; title and source filename; content; page/section metadata; and cosine similarity score. It returns evidence only and does not yet generate an answer.
