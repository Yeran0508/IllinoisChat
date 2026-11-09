# Illinois Chat Requirements

## 1. Purpose

This document defines the V1 product requirements for Illinois Chat. V1 is intentionally interview-oriented: all core resume-level capabilities must be implemented, tested, demonstrated, and measured before the release is called complete. Milestones define build order only; they do not defer core capabilities to a later product version.

## 2. Users and roles

### Student

- Ask questions about indexed course materials.
- Read grounded answers and inspect citations.
- Receive a clear refusal when the system lacks evidence.
- Receive bounded hints, rather than complete solutions, for protected assignments.

### Course administrator

- Add and remove course documents.
- Trigger ingestion and re-indexing.
- Inspect document processing failures.
- Review anonymized retrieval and quality metrics.

The first MVP may expose administrator operations through authenticated API endpoints or a command-line task. A full administrator UI is not required.

## 3. V1 baseline functional requirements

### FR-1 Document ingestion

- The system shall ingest PDF, Markdown, and plain-text files for one course.
- Each document shall have a stable identifier, title, course identifier, source filename, and ingestion status.
- Re-ingesting the same document version shall not create duplicate chunks.
- A failed document shall be reported without aborting the remaining ingestion batch.

**Acceptance criteria**

- A sample corpus containing all three supported formats can be ingested from a clean local environment.
- The API or ingestion task reports processed, skipped, and failed documents.

### FR-2 Structure-aware chunking

- The system shall preserve available page, heading, and section metadata.
- Markdown headings and fenced code blocks shall not be split in the middle unless they exceed the configured maximum size.
- Chunk size and overlap shall be configurable.

**Acceptance criteria**

- Every stored chunk can be traced back to its source document and location.
- Automated tests cover headings, code blocks, long sections, and empty documents.

### FR-3 Vector indexing and retrieval

- The system shall create embeddings for valid chunks and store them in a vector index.
- The query endpoint shall return the top-k chunks with scores and source metadata.
- The embedding model, top-k value, and similarity threshold shall be configurable.

**Acceptance criteria**

- A known-answer test set retrieves at least one relevant chunk within the configured top-k for an initial documented baseline.
- Re-indexing a document replaces stale chunks and embeddings.

### FR-4 Grounded question answering

- The system shall generate answers using only retrieved context.
- The answer shall include citations that identify the source document and location.
- The response shall distinguish answer text, citations, and request metadata.

**Acceptance criteria**

- Every factual answer sentence is associated with at least one retrieved source in the response data.
- A citation never points to a chunk that was absent from the retrieval context.

### FR-5 Insufficient-evidence refusal

- The system shall refuse to answer when retrieval evidence is absent or below a configurable sufficiency threshold.
- A refusal shall explain that the indexed materials do not provide enough support and may suggest related sources.
- The system shall not use unsupported model knowledge to fill gaps.

**Acceptance criteria**

- Out-of-domain questions in the evaluation set produce refusals.
- Refusal behavior is covered by automated integration tests.

### FR-6 Logging and evaluation data

- The system shall record a generated request ID, latency, retrieved chunk IDs and scores, citation IDs, refusal decision, and model configuration.
- Student text shall not be logged by default in production mode unless an explicit privacy policy permits it.
- Logs shall avoid secrets and raw credentials.

**Acceptance criteria**

- A request can be traced across retrieval and answer generation by request ID.
- Evaluation can run against stored, anonymized question records.

## 4. V1 advanced functional requirements

The following requirements are mandatory for V1 and are implemented after the baseline vertical slice.

### FR-7 Hybrid retrieval and reranking (M2)

- Combine BM25 keyword retrieval with vector retrieval.
- Fuse result lists with a documented algorithm such as reciprocal rank fusion.
- Rerank candidates with a configurable cross-encoder.
- Compare vector-only, hybrid, and reranked pipelines using Recall@5 and nDCG@10.
- Compare pgvector HNSW retrieval with `ef_search` set to `16`, `64`, and `256` while holding the corpus, query set, embedding model, index, top-k, hardware, and measurement procedure constant.
- Record retrieval quality together with P50 and P95 query latency for every HNSW configuration.

### FR-8 Homework protection (M3)

- Index assignment documents separately as protected material.
- Detect questions that substantially match protected assignments.
- Return configurable hint levels instead of final answers.
- Measure assignment-answer leakage on an adversarial evaluation set.

### FR-9 Citation validation and abstention (M3)

- Check whether each answer sentence is supported by cited evidence.
- Remove unsupported statements or refuse the complete response.
- Track citation precision and unsupported-claim rate.

### FR-10 Multi-hop retrieval (M4)

- Decompose cross-section questions into sub-questions.
- Retrieve evidence for each sub-question.
- Evaluate evidence sufficiency and repeat retrieval within a strict step limit.
- Preserve a trace linking the final answer to sub-questions and evidence.

### FR-11 Semantic caching (M5)

- Cache answers only when the normalized query, course/version, retrieval configuration, safety policy, and model configuration are compatible.
- Invalidate cache entries after relevant corpus changes.
- Measure cache hit rate, P95 latency, cost, and stale-answer rate.

## 5. Non-functional requirements

### Quality

- Retrieval and answer changes shall be evaluated against a versioned dataset before merge.
- The CI quality gate shall eventually cover retrieval, citation, refusal, and leakage metrics.
- Metric targets will be set only after a reproducible baseline is recorded; improvement percentages will not be hard-coded in advance.
- The first evaluation set shall contain 30-50 manually labeled questions spanning answerable, unanswerable, cross-section, code/formula, and protected-assignment cases.
- Any expansion toward 500 questions shall use questions that were actually collected or deliberately authored, anonymized where necessary, labeled, and reviewed. Dataset size shall never be inferred or claimed from a target alone.

### Experiment reproducibility

- Every benchmark or optimization claim shall have a report committed under `docs/experiments/`.
- Each report shall include the Git commit, dataset version and size, corpus version, model names and revisions, index and retrieval parameters, hardware/software environment, warm-up and repetition procedure, baseline, raw or machine-readable results, aggregated metrics, limitations, and conclusion.
- Comparisons shall change one intended variable at a time or explicitly document all confounding changes.
- Machine-readable result artifacts shall be retained when they contain no private or copyrighted data.
- README and resume performance claims shall link back to a reproducible report.

### Performance

- The MVP shall record P50 and P95 latency for retrieval and complete responses.
- All external model calls shall have timeouts and bounded retries.
- Expensive ingestion work shall not run inside a synchronous query request.

### Security and privacy

- Secrets shall be loaded from environment variables and excluded from Git.
- Uploaded files shall be validated by type and size.
- Course data shall be isolated by course identifier before multi-course access is enabled.
- Evaluation datasets derived from student questions shall be anonymized.
- Logs shall not contain API keys, credentials, or unnecessary personal information.

### Reliability and maintainability

- Database migrations shall be version controlled.
- Core retrieval and safety components shall depend on interfaces rather than a single model vendor.
- Unit tests shall cover chunking and ranking logic; integration tests shall cover ingestion-to-answer flows.
- Local dependencies shall be reproducible through Docker Compose.

## 6. Initial API surface

The exact schemas will be finalized during M0.

| Method | Path | Purpose | Milestone |
|---|---|---|---|
| `GET` | `/api/v1/health` | API liveness; confirms the process and HTTP routing are available | M0 |
| `POST` | `/api/v1/documents` | Upload/register a course document | M1 |
| `POST` | `/api/v1/documents/{id}/ingest` | Process and index a document | M1 |
| `GET` | `/api/v1/documents/{id}` | Read ingestion status and metadata | M1 |
| `DELETE` | `/api/v1/documents/{id}` | Remove a document and its chunks | M1 |
| `POST` | `/api/v1/retrieval/search` | Inspect retrieved chunks for a query | M1 |
| `POST` | `/api/v1/chat` | Produce a grounded answer or refusal | M1 |
| `POST` | `/api/v1/evaluations/run` | Run a versioned offline evaluation | M2 |

## 7. V1 completion definition

V1 is complete only when:

1. A new developer can start the stack from documented commands.
2. The sample course corpus can be ingested repeatedly without duplication.
3. BM25 and vector search results are fused and reranked by a cross-encoder.
4. A relevant question produces a sentence-level cited answer.
5. An unsupported question produces a refusal based on an evidence-sufficiency decision.
6. A cross-section question can invoke bounded decomposition and iterative retrieval.
7. A protected assignment question returns a configured hint level without a final answer.
8. Semantic caching is version-aware, invalidates after corpus changes, and exposes hit-rate and latency metrics.
9. Automated tests exercise the complete ingestion-to-answer path.
10. A versioned evaluation set measures Recall@5, nDCG@10, citation quality, refusal quality, and assignment leakage.
11. The initial 30-50 question evaluation set is manually labeled and reviewed.
12. HNSW `ef_search = 16`, `64`, and `256` results are recorded with recall and P50/P95 latency under controlled conditions.
13. Retrieval, citation, refusal, and leakage regression checks run in CI.
14. Every reported improvement has a reproducible experiment report containing its baseline, parameters, data, environment, and results.
15. An interview demo script and architecture explanation reproduce the principal workflows and trade-offs.
16. No secret or private course material is committed to Git.
17. CI passes on the default branch.

## 8. Explicitly out of scope for V1

- Multi-course tenancy and role-management UI.
- Real-time chat over WebSocket.
- Fine-tuning or training a foundation model.
- Voice or image-based questions.
- Native mobile applications.
- High-availability production deployment.
- Fabricated claims about traffic, quality improvements, cache hit rate, or latency reduction before measured evidence exists.

## 9. M0 technical decisions

- Model, embedding, and reranking providers remain behind interfaces. Local development will use an OpenAI-compatible chat interface (with Ollama as the no-key option), BGE embeddings, and a BGE cross-encoder reranker. Exact model sizes will be selected by measured quality and local resource use during M1/M2.
- PostgreSQL + pgvector is selected as the baseline vector store.
- OpenSearch is selected for V1 BM25 retrieval and will be integrated in M2.
- The committed sample corpus will be author-created synthetic computer-science course material. Private student questions and copyrighted course files will not be committed.
- Evaluation records will include answerability, graded passage relevance, required evidence, citation support, and protected-assignment labels. The first versioned dataset will be created alongside the M1 ingestion pipeline.
- The React frontend begins after the backend quality baseline; an interview-ready UI is required before V1 completion.
