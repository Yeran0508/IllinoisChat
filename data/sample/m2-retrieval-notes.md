# Information Retrieval

## BM25

BM25 is a lexical ranking function based on term frequency, inverse document frequency, and document-length normalization. Its k1 parameter controls term-frequency saturation, while b controls length normalization.

## Dense Retrieval

Dense retrieval embeds queries and passages into vectors. Cosine similarity can retrieve semantically related passages even when query and document use different vocabulary.

## HNSW

HNSW is an approximate nearest-neighbor graph index. Increasing ef_search examines more candidates and can improve recall at the cost of query latency.

## Reciprocal Rank Fusion

Reciprocal Rank Fusion combines ranked lists without requiring their raw scores to share a scale. Each result receives 1 divided by k plus its rank in each list.

## Cross-Encoder Reranking

A cross-encoder jointly processes a query and candidate passage to estimate relevance. It is more expensive than first-stage retrieval, so it reranks a bounded candidate set.

# Evaluation

## Recall at K

Recall at K is the fraction of all relevant items retrieved within the first K results. It emphasizes whether relevant evidence was found.

## NDCG

Normalized Discounted Cumulative Gain supports graded relevance and rewards placing highly relevant results near the top. It divides DCG by the ideal ranking's DCG.

## Latency Percentiles

P50 is the median latency. P95 is the value at or below which 95 percent of observations fall and exposes tail latency better than an average alone.

# RAG Reliability

## Grounded Answers

A grounded answer uses only retrieved evidence. Every factual sentence should identify supporting evidence from the retrieval context.

## Abstention

The system should abstain when no evidence is retrieved, similarity is below a calibrated threshold, or the available passages do not fully support the answer.

## Citation Validation

Citation IDs must be validated against the exact chunks supplied to the model. An unknown citation ID makes the generated answer unsafe to return.

# Data Engineering

## Idempotent Ingestion

Content hashes and database uniqueness constraints prevent repeated uploads of the same document version from creating duplicate chunks.

## Versioning

A logical Document has immutable DocumentVersion snapshots. Versioning supports reproducible evaluation and corpus-aware cache invalidation.

## Transactions

Chunk replacement and version completion belong to one database transaction. On failure, partial database changes are rolled back and the version is marked failed.

## Privacy

Audit logs avoid raw student questions and credentials. The baseline records a query hash, decisions, latency, model identity, and retrieved or cited chunk IDs.
