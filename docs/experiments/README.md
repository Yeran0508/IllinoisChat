# Experiment Reports

This directory stores reproducible evidence for retrieval, safety, caching, cost, and latency claims. Create one Markdown report per experiment and keep non-sensitive machine-readable results beside it when practical.

Suggested filename: `YYYY-MM-DD-short-experiment-name.md`.

## Required report template

```markdown
# Experiment: <name>

## Question

What single question or hypothesis does this experiment test?

## Reproducibility metadata

- Date:
- Git commit:
- Dataset name/version:
- Corpus name/version and document/chunk counts:
- Hardware and operating system:
- Python and dependency versions:
- Model names and exact revisions:
- Index type and build parameters:
- Query-time parameters:
- Random seed, if applicable:

## Procedure

Describe warm-up, repetitions, timing boundaries, relevance judgments, metrics, and the variable being changed. Identify controlled variables and known confounders.

## Baseline

Describe the current system and its measured results before the change.

## Results

Link machine-readable output and report sample size, Recall@5, nDCG@10, P50/P95 latency, or other metrics relevant to the hypothesis. Include failures and negative results.

## Analysis

Explain the quality, latency, memory, cost, and operational trade-offs. Do not infer causation beyond the controlled experiment.

## Limitations

List dataset, labeling, measurement, hardware, and generalization limitations.

## Decision

State whether the change is adopted and why. Record follow-up experiments.
```

## Required HNSW comparison

The V1 HNSW report must compare `ef_search = 16`, `64`, and `256` against the same built index. It must keep the corpus, evaluation questions, embedding model, distance function, top-k, hardware, and timing method fixed, and report retrieval recall plus P50/P95 latency for each value.
