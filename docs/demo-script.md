# Illinois Chat interview demo

Target length: 8–10 minutes. Run `scripts/demo.sh` first to prepare the sample course, or follow the UI upload flow at `http://localhost:4173`.

## 1. Frame the problem — 45 seconds

“Course information is fragmented across prose, formulas, and code. Plain keyword search misses paraphrases, while an unconstrained LLM can invent an answer or disclose a protected assignment. Illinois Chat combines hybrid retrieval with explicit evidence and safety gates.”

Point out the UI promise: evidence, refusal, and bounded hints are distinct response states—not presentation variants of the same free-form model output.

## 2. Ingest and version a source — 60 seconds

Open **Course admin**, upload `data/sample/m2-retrieval-notes.md`, and register it as ordinary material. Explain:

- raw bytes receive SHA-256;
- the same source and content reuse an immutable `DocumentVersion`;
- structure-aware chunks preserve headings and code;
- BGE vectors go to pgvector and ordinary chunks are synchronized to OpenSearch.

Upload the same file again and show `reused: true` through the script/API. This demonstrates idempotency rather than merely describing it.

## 3. Grounded answer and source ledger — 90 seconds

Ask: **“How does reciprocal rank fusion combine BM25 and vector rankings?”**

Show sentence citation markers, the source ledger, source section, evidence excerpt, retrieval score, request ID, model name, and latency. Explain that RRF combines ranks without requiring BM25 and vector scores to share a scale; a cross-encoder then jointly scores query-passage pairs.

Emphasize that citation IDs are checked against retrieved chunks and a separate support pass checks whether each sentence is entailed by its cited evidence.

## 4. Multi-part trace and refusal — 90 seconds

Ask: **“Why do immutable document versions help evaluation and cache invalidation?”**

Walk through the bounded subquestions and stop reason. Explain the hard limits: at most the configured number of subquestions, follow-ups, and retrieval steps. Missing evidence after the limit produces `iterative_evidence_insufficient` rather than an unbounded agent loop.

Then ask: **“Who won the 2026 World Series?”** Show the explicit insufficient-evidence response. The model is not permitted to fill the gap from unsupported world knowledge.

## 5. Protected assignment route — 90 seconds

Ensure `data/sample/m3-protected-homework.md` is ingested with `is_protected=true`. Ask for the complete implementation of Homework 1 Question 2.

Show `homework_hint`, the hint level, and the absence of protected source citations. Explain defense in depth:

- protected chunks are absent from ordinary BM25;
- ordinary pgvector retrieval filters them out;
- protected-only matching happens before normal retrieval and generation;
- the response offers allowed conceptual help instead of a solution.

## 6. Semantic cache and invalidation — 75 seconds

Repeat the grounded RRF question. Show `Cache hit`, similarity, and updated metrics. Explain that similarity alone is insufficient: course corpus, retrieval, safety, and model hashes must match exactly.

Register a changed version, ingest it, and repeat. The corpus fingerprint changes, the old entry is rejected, and the service makes a fresh upstream call. Do not quote the controlled 98.36% hit rate as expected production traffic; it came from one deliberately repeated query.

## 7. Evidence and trade-offs — 90 seconds

Open the architecture document and summarize:

- 70 backend tests passed with 91.51% coverage at the M5 checkpoint;
- UI type checking, component tests, and production build run in CI;
- M2, M3, and M5 reports preserve raw data and negative baselines;
- PostgreSQL/OpenSearch dual writes use compensation, not distributed atomicity;
- M3’s small synthetic safety set and M5’s simulated upstream limit generalization;
- held-out real-LLM multi-hop quality and production load remain separate claims.

Close with: “The project’s main engineering theme is not adding more model calls. It is making every expensive or risky decision bounded, observable, and testable.”

## Recovery plan

- If the LLM provider is unavailable, show retrieval and protected-hint paths, then explain that ordinary answer generation correctly returns `503`; do not substitute fake output in a live demo.
- If OpenSearch is unhealthy, use `docker compose ps` and show that readiness differs from liveness.
- If Redis is unavailable, chat should fall back to uncached generation; `/metrics` should return `503`.
