# Illinois Chat V1 architecture

This document explains the runtime data flow, trust boundaries, and deliberate V1 trade-offs used in the interview demo.

## System context

```text
Student / course administrator
              |
              v
      React + nginx :4173
              |
              v
         FastAPI :8000
      /        |         \
     v         v          v
PostgreSQL  OpenSearch   Redis
+ pgvector    BM25     semantic cache
     |                     |
     +----------+----------+
                v
       OpenAI-compatible LLM
       BGE embedding/reranker
```

The browser talks to nginx on one origin. Nginx serves the static React build and proxies `/api` to FastAPI. Development may instead use the Vite proxy or the configured CORS allowlist. PostgreSQL is the system of record; OpenSearch and Redis are derived/query-serving stores.

## Ingestion flow

```text
upload -> validate size/type -> SHA-256 -> create/reuse immutable version
                                      |
                                      v
                      parse -> structure-aware chunks -> BGE vectors
                                      |
                   +------------------+------------------+
                   v                                     v
          PostgreSQL + pgvector                 OpenSearch BM25
```

- A logical `Document` has immutable `DocumentVersion` records. Content hashes plus database uniqueness constraints make repeated registration idempotent.
- Parsing preserves Markdown sections, fenced code, and PDF pages. Each chunk carries source metadata for citations.
- Chunk replacement and version completion are transactional in PostgreSQL. OpenSearch synchronization uses compensating cleanup, not a distributed transaction. A production design would add an outbox, retry worker, and reconciliation job.
- Protected assignment chunks retain vectors for protected-only matching but are excluded from ordinary pgvector and BM25 answer retrieval.

## Question-answering flow

```text
query
  |
  v
protected identity + intent matcher ---- match ----> bounded hint, no answer LLM
  |
 no match
  v
cache compatibility -> semantic hit -------------> cached grounded answer
  |
 miss
  v
bounded decomposition -> vector + BM25 -> RRF -> cross-encoder
  |                                             |
  +---- evidence sufficiency / follow-up <------+
                          |
             insufficient+------sufficient
                  |                    |
                refuse          answer-model JSON
                                       |
                         citation allowlist + sentence support
                                |                 |
                              fail              pass
                                |                 |
                              refuse       answer + citations
```

The order is intentional. Assignment safety runs before ordinary retrieval and generation. Cache candidates must exactly match the course corpus fingerprint plus retrieval, safety, and model configuration hashes before query-vector similarity is considered. Multi-part retrieval has hard limits on subquestions, follow-ups, and steps. Generation fails closed on insufficient evidence, malformed output, fabricated citation IDs, or unsupported sentences.

## Cache invalidation and observability

The corpus fingerprint hashes every completed version's document ID, version ID, content digest, and protected flag in stable order. A newly completed version changes the fingerprint, so an old entry is rejected rather than served. Only standard grounded answers are cached; refusals and homework hints are not.

Redis records hit/miss counts, incompatible-entry rejections, stale answers served, and a bounded recent latency sample. `/api/v1/metrics` exposes the snapshot. Redis failure is fail-open for chat—the normal answer path remains available—but the metrics endpoint returns `503` when its store is unavailable.

## Security and privacy boundaries

- API keys and database credentials come from environment variables. `.env` and private uploads are excluded from Git.
- Upload size and media type are bounded before parsing. Local storage prevents path traversal.
- Request audit records store normalized query SHA-256 instead of raw student text. Hashing is not encryption; production should use keyed hashing, access control, and retention limits.
- Course filtering is enforced in retrieval queries. V1 supports one administrator boundary, not production multi-tenant authorization.
- Retrieved documents are untrusted data, not executable instructions. A dedicated document-borne prompt-injection evaluation remains future work.

## What the evidence proves—and does not prove

The automated suite verifies deterministic behavior and real PostgreSQL/pgvector, OpenSearch, and Redis integration. Versioned reports preserve M2 retrieval, M3 assignment-safety, and M5 cache experiments. These artifacts do not prove production-scale latency, universal safety, or real-LLM answer quality. The M5 upstream is simulated; the M3 set is small and partly policy-shaped; M4 still needs a held-out real-model quality study.

## V1 trade-offs and next production steps

| V1 choice | Benefit | Production follow-up |
|---|---|---|
| FastAPI background ingestion | Small local deployment | Durable queue, retries, idempotent workers |
| PostgreSQL/OpenSearch compensating dual write | Simple hybrid baseline | Transactional outbox and reconciliation |
| Bounded Redis set candidate scan | Auditable semantic cache | Redis vector index or dedicated ANN cache |
| Rule + embedding assignment matcher | Explainable safety path | Held-out multi-assignment classifier and red-team set |
| Single administrator/course boundary | Focused interview scope | Authentication, authorization, tenancy, audit retention |
