# Experiment: M2 retrieval baseline

## Question

How do vector-only, BM25-only, and RRF plus cross-encoder retrieval compare on the synthetic M2 corpus, and how do HNSW ef_search values 16, 64, and 256 compare when other variables are fixed?

## Evidence status

All 30 labels were subsequently reviewed by the project author without changing the queries, answerability, relevant sections, or relevance grades. The raw artifact predates that status update, so its review-status count is stale, but its retrieval metrics remain computed from the same unchanged judgments. Corpus-size limitations still make the quality result unsuitable as a broad production claim.

## Reproducibility metadata

- Date: 2026-11-10
- Git base commit: 2b8ad3993ef78b44ab9fce315e595b95cf30a267
- M2 implementation commit: 03af407
- Evidence status: implementation and raw artifact are committed; all labels were subsequently manually reviewed without judgment changes.
- Dataset: data/evaluation/m2-v1.jsonl, 30 total cases, 28 answerable and scored
- Corpus: data/sample/m2-retrieval-notes.md, one document and 34 chunks
- Environment: Docker Desktop Linux 6.10.14-linuxkit x86_64; Python 3.12.10
- Embedding: BAAI/bge-small-en-v1.5, 384 dimensions
- Reranker: Xenova/ms-marco-MiniLM-L-6-v2
- Vector index: pgvector HNSW with cosine distance
- Lexical index: OpenSearch 2.19.1 default BM25
- Hybrid: vector top 20 plus BM25 top 20, RRF constant 60, then cross-encoder
- Query top-k: 10 for nDCG; Recall reported at 5
- Timing: every answerable query repeated 5 times; 140 observations per pipeline/configuration
- Raw results: [m2-baseline.json](results/m2-baseline.json)

## Procedure

The runner deletes only the prior synthetic CS-RAG sample document, ingests the committed Markdown corpus through the production parser, chunker, BGE embedder, pgvector storage, and OpenSearch indexing path, then runs the same dataset against each pipeline. Quality uses the first ranking per query. All five repetitions contribute to latency. Duplicate chunks from the same labeled section receive relevance credit only on their first occurrence.

For HNSW, the corpus, query set, embedding model, built index, cosine distance, top-k, container, and timing code remained fixed. Only transaction-local hnsw.ef_search changed.

## Results

| Pipeline | Recall@5 | nDCG@10 | Mean ms | P50 ms | P95 ms |
|---|---:|---:|---:|---:|---:|
| Vector, ef=64 | 1.0000 | 0.9736 | 17.09 | 16.39 | 24.85 |
| BM25 | 1.0000 | 0.9643 | 9.25 | 9.06 | 10.92 |
| RRF + cross-encoder | 1.0000 | 0.9868 | 277.63 | 259.94 | 370.47 |

| HNSW ef_search | Recall@5 | nDCG@10 | Mean ms | P50 ms | P95 ms |
|---:|---:|---:|---:|---:|---:|
| 16 | 1.0000 | 0.9736 | 16.59 | 15.34 | 26.38 |
| 64 | 1.0000 | 0.9736 | 20.64 | 18.91 | 34.39 |
| 256 | 1.0000 | 0.9736 | 21.70 | 16.87 | 34.51 |

## Analysis

Hybrid reranking produced the best draft nDCG, but its P95 latency was roughly fifteen times the vector baseline because the CPU cross-encoder scores up to 20 candidates. BM25 was fastest on this tiny exact-vocabulary corpus. All pipelines achieved perfect Recall@5, so this dataset is too easy to demonstrate recall improvement.

The HNSW rankings were identical. Latency generally increased with larger ef_search, but ef=16 had a noisy P95. With only 34 chunks, fixed runtime overhead dominates graph-search work; these numbers do not establish a production setting.

## Limitations

- The raw artifact records the pre-review status string; labels were subsequently reviewed without judgment changes.
- The synthetic corpus has only 34 chunks and substantial vocabulary overlap with queries.
- Only 28 answerable questions contribute to retrieval metrics.
- Measurements use a local Docker CPU environment and include embedding time.
- No confidence intervals or multi-process load were measured.
- Model revisions are names, not immutable artifact hashes.

## Decision

Adopt the hybrid pipeline as the M2 implementation default because it satisfies the architecture requirement and has the strongest ranking quality on this reviewed synthetic set. Do not claim the measured difference as a general improvement on the resume until the corpus is expanded. Keep ef_search=64 as a conservative default; the present corpus is too small to justify changing it from quality evidence.
