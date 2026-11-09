# Illinois Chat

Illinois Chat is a campus-oriented retrieval-augmented generation (RAG) question-answering platform. It helps students find information in course materials while keeping answers grounded in cited sources and avoiding direct disclosure of homework solutions.

> Project status: planning and V1 implementation. The capabilities below are V1 acceptance targets, not completed claims.

Current checkpoint: **M0 foundation completed and locally verified**. M1 ingestion and vector-retrieval work has not started.

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
- [`IllinoisChat学习笔记.txt`](IllinoisChat学习笔记.txt): verified implementation notes and interview explanations, updated throughout development.
- [`docs/api-contract.md`](docs/api-contract.md): contracts for endpoints already introduced in code.

## Local development

Requirements: Docker Desktop with Docker Compose.

```bash
cp .env.example .env
docker compose up --build -d api postgres
curl http://localhost:8000/api/v1/health
```

Run the backend quality checks in the reproducible Python 3.12 test image:

```bash
docker build --target test -t illinois-chat-test .
docker run --rm illinois-chat-test ruff check .
docker run --rm illinois-chat-test pytest -o cache_dir=/tmp/pytest_cache --cov=app --cov-report=term-missing --cov-fail-under=90
docker compose config --quiet
```

OpenSearch and Redis are declared for the complete V1 but are opt-in until their application integrations are implemented:

```bash
docker compose --profile full up -d
```

## License

No license has been selected yet.
