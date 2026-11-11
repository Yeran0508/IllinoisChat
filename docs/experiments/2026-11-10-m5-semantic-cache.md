# Experiment: M5 semantic-cache baseline and exact-query embedding reuse

## Question

Does a corpus-aware Redis semantic cache avoid repeated upstream answer calls without serving an entry after the corpus changes, and does reusing an exact query embedding reduce warm-cache contention?

## Evidence status

This is a controlled cache-layer experiment. It uses real Redis and real BGE query embeddings, but a deterministic 50 ms simulated upstream answer service. It is not a production traffic, real-LLM latency, answer-quality, or dollar-cost measurement.

## Reproducibility metadata

- Date: 2026-11-10 (America/Chicago)
- Git base commit: `980bc2d`; the M5 implementation was an uncommitted working tree when measured
- Workload: one cold request, 20 sequential warm requests, 100 warm requests with 10 worker threads, and one request after a controlled corpus-fingerprint change
- Query: one repeated synthetic RRF question; no student or private data
- Environment: Docker Desktop, Linux 6.10.14-linuxkit x86_64, Python 3.12.10
- Redis: 7.4.3-alpine
- Embedding model: `BAAI/bge-small-en-v1.5`, using the FastEmbed provider
- Cache parameters: cosine threshold 0.94, TTL 3600 seconds, maximum 100 candidate entries per course
- Compatibility fields: course code, corpus fingerprint, retrieval configuration hash, safety-policy hash, and model-configuration hash
- Upstream: deterministic answer service with a 50 ms sleep
- Raw baseline: [m5-cache-baseline.json](results/m5-cache-baseline.json)
- Raw optimized result: [m5-cache-optimized.json](results/m5-cache-optimized.json)

## Procedure

The runner clears Illinois Chat cache keys, creates one service using the production Redis cache and BGE embedding adapter, and sends the same normalized query through the full cache wrapper. The first request is a cold miss and is eligible for storage because its result is a normal grounded-answer status. Twenty sequential requests then exercise the warm path.

Next, a `ThreadPoolExecutor` sends 100 warm requests with 10 workers. Timing includes corpus fingerprint construction in the controlled provider, query-vector lookup or computation, Redis candidate reads, cosine comparison, result deserialization, and metric writes. It excludes network ingress and a real generation model.

Finally, the runner changes the controlled corpus fingerprint from `corpus-v1` to `corpus-v2` and asks the same question. The expected result is a miss, a stale-rejection counter increment, and another upstream call. The implementation never falls back to a stale value.

The baseline computes the same BGE query embedding for every lookup. Inspection of its negative concurrent result led to one intentional change: an instance-local, thread-safe, 1024-entry exact-query LRU. The second run keeps the Redis, BGE model, workload, query, threshold, TTL, candidate limit, worker count, and simulated upstream delay fixed.

## Baseline

| Measurement | Baseline |
|---|---:|
| Cold request | 82.56 ms, miss |
| Sequential warm P50 / P95 | 11.15 / 13.67 ms |
| Concurrent warm P50 / P95 | 84.19 / 223.68 ms |
| 100-request concurrent wall time | 1063.11 ms |
| After corpus change | 78.01 ms, miss |

The concurrent warm path was slower than the 50 ms simulated upstream at P95. Profiling the request boundary showed repeated CPU-bound BGE inference for an identical normalized query. This negative result means that Redis alone did not make the tested warm path efficient under local concurrency.

## Results

| Measurement | Baseline | Exact-query LRU | Observed change |
|---|---:|---:|---:|
| Sequential warm P50 | 11.15 ms | 1.05 ms | lower by 90.6% |
| Sequential warm P95 | 13.67 ms | 2.85 ms | lower by 79.1% |
| Concurrent warm P50 | 84.19 ms | 21.57 ms | lower by 74.4% |
| Concurrent warm P95 | 223.68 ms | 51.19 ms | lower by 77.1% |
| 100-request concurrent wall time | 1063.11 ms | 281.26 ms | lower by 73.5% |
| Cache hits / misses | 120 / 2 | 120 / 2 | unchanged |
| Stale rejections | 1 | 1 | unchanged |
| Stale answers served | 0 | 0 | unchanged |
| Upstream calls / avoided calls | 2 / 120 | 2 / 120 | unchanged |

The measured hit rate was 120/122, or 98.36%, because the workload was deliberately pre-warmed and repeated one query. It is evidence about this workload only, not a forecast for user traffic. The post-change request missed in both runs, so the observed stale-answer rate was zero and one incompatible entry was rejected.

## Analysis

The cache key is not just a query string. A candidate is eligible only when its course and four configuration/corpus compatibility fields match exactly; cosine similarity is evaluated afterward. The corpus fingerprint hashes every completed immutable document version, content digest, document ID, and protection flag for that course. Adding a completed version therefore changes the fingerprint without requiring a broad Redis delete.

Only `answered` results in standard safety mode are written. Refusals and protected-assignment hints bypass storage, avoiding reuse of context-sensitive safety responses. Redis failures fail open to the normal answer service, while the metrics endpoint reports Redis failure as unavailable.

The optimization removes redundant exact-query BGE inference. It does not make semantic similarity approximate in memory: different strings still receive their own BGE vectors and are compared against Redis entries. The LRU is bounded at 1024 entries and uses a lock so concurrent identical requests do not stampede the embedder. The trade-off is per-process memory plus serialization of query-embedding cache misses.

Avoided upstream calls are a cost proxy only. No provider price or real token count was measured, so no dollar-saving claim is supported.

## Limitations

- One repeated pre-warmed query makes the 98.36% hit rate intentionally optimistic and unsuitable for capacity planning.
- The upstream is a fixed 50 ms simulator, not an LLM; complete-response latency and monetary cost remain unmeasured.
- The experiment does not test a cold-key cache stampede, diverse paraphrases, eviction behavior, Redis persistence recovery, or more than 100 candidates.
- The corpus fingerprint is changed directly to isolate invalidation. A separate PostgreSQL integration test verifies that ingesting another completed version changes the production fingerprint.
- The two runs are sequential on one laptop rather than statistically randomized trials; cold-start differences and host load are confounders.
- `stale_answer_rate = 0` means no stale answer was observed in 122 requests. It is not proof that every future invalidation path is correct.
- Candidate membership currently uses a bounded Redis set scan. A larger deployment should evaluate a Redis vector index or another ANN cache index.

## Decision

Adopt the compatibility-gated Redis cache and the bounded exact-query embedding LRU for V1. Keep both raw runs, including the poor concurrent baseline, because the negative result explains the optimization. Before making production or resume percentage claims, repeat with diverse anonymized queries, a real configured LLM, multiple corpus updates, cold-key concurrency, token/cost accounting, and sustained load.
