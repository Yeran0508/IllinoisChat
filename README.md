# Illinois Chat

Illinois Chat is a campus-oriented retrieval-augmented generation (RAG) question-answering platform. It helps students find information in course materials while keeping answers grounded in cited sources and avoiding direct disclosure of homework solutions.

> Project status: planning and V1 implementation. The capabilities below are V1 acceptance targets, not completed claims.

Current checkpoint: **M0 and the M1 end-to-end RAG baseline are implemented and locally verified**. Measured retrieval-quality improvements remain M2 work.

## Problem

Course content is spread across slides, notes, code samples, formulas, and assignment documents. Traditional keyword search often misses semantic matches, while an unconstrained language model can hallucinate or reveal complete homework answers.

Illinois Chat is designed to:

- retrieve relevant passages from course materials;
- answer only when the retrieved evidence is sufficient;
- attach source citations to claims;
- refuse unsupported questions;
- provide hints instead of direct answers for detected homework questions.

## V1 scope

V1 is an interview-ready, end-to-end implementation of the project's core technical claims. It will support one course and one administrator while including:

1. Ingest PDF, Markdown, and text course materials.
2. Parse and chunk documents while preserving document, section, and page metadata.
3. Retrieve with BM25 and vector search, fuse results, and rerank with a cross-encoder.
4. Decompose cross-section questions and perform bounded iterative retrieval.
5. Generate grounded answers with sentence-level source citations.
6. Refuse unsupported questions after an explicit evidence-sufficiency check.
7. Detect protected assignment questions and return tiered hints instead of final answers.
8. Run retrieval, citation, refusal, and leakage evaluations in CI.
9. Cache semantically similar questions with corpus-aware invalidation.
10. Record retrieval quality, latency, cache, citation, refusal, and leakage metrics.

Authentication beyond a minimal administrator boundary, multi-course tenancy, native mobile clients, and high-availability production deployment remain outside V1. Traffic volume and percentage-improvement claims will be reported only after reproducible measurement.

## V1 implementation milestones

- **M0 - Foundation:** repository structure, local configuration, Docker Compose, health check, and CI.
- **M1 - RAG baseline:** document ingestion, structure-aware chunking, embeddings, vector retrieval, grounded answers, citations, and refusal.
- **M2 - Retrieval quality:** BM25 + vector hybrid retrieval, rank fusion, cross-encoder reranking, and an offline evaluation set.
- **M3 - Safety:** assignment detection, configurable hint levels, sentence-level citation validation, and leakage evaluation.
- **M4 - Advanced retrieval:** question decomposition, iterative retrieval, and evidence sufficiency checks.
- **M5 - Performance:** semantic cache, index tuning, observability, load testing, and latency/cost optimization.

All milestones M0-M5 are required for the V1 release. Milestones are implementation checkpoints, not deferred product versions.

### Current M1 implementation

- SQLAlchemy models and Alembic migration for courses, logical documents, content-addressed document versions, and chunks.
- A 384-dimensional pgvector column with an HNSW cosine-distance index, ready for the M1 embedding baseline.
- PDF, UTF-8 Markdown, and plain-text parsing into a shared block representation.
- Markdown heading hierarchy and fenced code-block preservation.
- Configurable structure-aware chunking with source page/section metadata, stable indexes, overlap, and SHA-256 content hashes.
- Migration upgrade/downgrade checks in CI and local Docker Compose startup.
- Multipart document registration with bounded uploads, persistent source storage, content-hash version reuse, and `pending/processing/completed/failed` state tracking.
- FastEmbed integration for `BAAI/bge-small-en-v1.5`; real local inference is verified to produce normalized 384-dimensional document and query vectors.
- Transactional Chunk and Embedding persistence, with failed ingestion recorded on the document version.
- Configurable pgvector cosine retrieval with `hnsw.ef_search`, course filtering, source metadata, and similarity scores.
- Document registration, status, ingestion, deletion, and vector-search API contracts.
- OpenAI-compatible chat-model boundary, usable with Ollama locally or another compatible provider through configuration.
- Grounded answer generation with a retrieval-score gate, model evidence-sufficiency decision, and safe refusal paths.
- Sentence-level citation IDs validated against the exact retrieved context, with document/page/section evidence in the response.
- Privacy-preserving request audit records containing a query hash, latency, decisions, retrieved/cited chunk IDs, and model name rather than raw student text.

M1 establishes a functional baseline, not a measured quality claim. Hybrid retrieval, reranking, a manually reviewed 30-50 question evaluation set, and controlled HNSW experiments remain M2 work.

## Evaluation evidence policy

V1 results must come from reproducible experiments rather than assumed improvements:

- Start with a manually labeled evaluation set of 30-50 questions, covering answerable, unanswerable, cross-section, code/formula, and protected-assignment cases. Expand it only with collected, anonymized, labeled, and reviewed examples.
- Run a controlled HNSW experiment with `ef_search = 16`, `64`, and `256`. Keep the corpus, queries, embedding model, index, top-k, hardware, and measurement procedure fixed; compare retrieval recall with P50/P95 latency.
- Store experiment reports under `docs/experiments/`. Every report must identify the code revision, data version and size, parameters, environment, procedure, baseline, raw/aggregated results, limitations, and conclusion.
- Do not claim a 500-question dataset, quality improvement, cache hit rate, traffic volume, or latency reduction until the underlying data and report exist.

## Proposed architecture

```text
React client
    |
FastAPI application
    |-- ingestion and chunking pipeline
    |-- retrieval and reranking pipeline
    |-- answer, citation, and safety pipeline
    |-- evaluation and observability
    |
    |-- PostgreSQL + pgvector
    |-- Elasticsearch/OpenSearch (hybrid retrieval milestone)
    `-- Redis (semantic caching milestone)
```

The model and embedding providers will be accessed behind interfaces so they can be replaced without rewriting the retrieval pipeline.

## Repository documents

- [`requirements.md`](requirements.md): product requirements, acceptance criteria, non-functional requirements, and phased scope.
- [`docs/api-contract.md`](docs/api-contract.md): contracts for endpoints already introduced in code.
- [`docs/experiments/README.md`](docs/experiments/README.md): required template and evidence rules for reproducible experiments.

## Local development

Requirements: Docker Desktop with Docker Compose.

```bash
cp .env.example .env
docker compose up --build -d api postgres
curl http://localhost:8000/api/v1/health
```

For local generation, start an OpenAI-compatible provider and configure `LLM_BASE_URL` and `LLM_MODEL`. The defaults target Ollama on the Docker host with `qwen3:4b`; the model is not downloaded automatically.

Run the backend quality checks, including PostgreSQL integration tests, in reproducible Python 3.12 containers:

```bash
docker compose --profile test build migrate test
docker compose run --rm migrate
docker compose --profile test run --rm --no-deps test
docker compose config --quiet
```

OpenSearch and Redis are declared for the complete V1 but are opt-in until their application integrations are implemented:

```bash
docker compose --profile full up -d
```

## License

No license has been selected yet.
