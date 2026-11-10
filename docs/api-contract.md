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

Retrieves vector and OpenSearch BM25 candidates for one course, fuses them with reciprocal rank fusion, and reranks the bounded candidate set with a cross-encoder.

```json
{
  "course_code": "CS411",
  "query": "How does an HNSW index trade recall for latency?",
  "top_k": 5
}
```

The response returns source IDs and metadata, normalized final score, and `retrieval_metadata` containing available component scores, ranks, RRF score, reranker logit, and model name.

## `POST /api/v1/evaluations/run`

Runs the configured versioned dataset against hybrid retrieval. The response contains case counts, Recall@5, nDCG@10, mean/P50/P95 latency, and review-status counts. The committed dataset remains `pending_human_review`, so the output is provisional evidence.

## `POST /api/v1/chat`

Retrieves course evidence and returns either a grounded answer or an explicit refusal.

```json
{
  "course_code": "CS411",
  "query": "How does HNSW trade recall for latency?"
}
```

An answered response contains `sentences`, where every item has one or more `citation_ids`. Each ID must resolve to a `citations` item backed by a chunk from `retrieved_chunk_ids`. Citation objects include document/version/chunk IDs, source name, page or section metadata, a bounded evidence excerpt, and retrieval score.

A safe refusal returns `status: "insufficient_evidence"`, no answer sentences or citations, and one of the machine-readable reasons: `no_evidence`, `low_retrieval_score`, `model_insufficient_evidence`, `invalid_model_output`, or `invalid_citation`. Model-provider failures return `503` without exposing provider details.

The server records request ID, latency, model name, outcome, retrieval score, and retrieved/cited chunk IDs. It stores SHA-256 of the normalized query instead of raw student text.
