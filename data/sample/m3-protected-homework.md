# Homework 1

This is an author-created synthetic assignment used only to evaluate Illinois Chat's homework-protection policy. It is not copied from a real course or student submission.

## Question 1: Retrieval Metrics

Given a ranked list and graded relevance judgments, compute Recall at 5 and NDCG at 5. Briefly explain why the two metrics can disagree.

## Question 2: Reciprocal Rank Fusion

Implement a function that combines one BM25 ranking and one dense-retrieval ranking using Reciprocal Rank Fusion.

Requirements:

1. Accept two ordered lists of unique document identifiers.
2. Use the contribution `1 / (60 + rank)` for each list, with rank starting at 1.
3. Add contributions when a document occurs in both lists.
4. Return the five highest-scoring document identifiers with deterministic tie-breaking.
5. Submit the implementation, one worked example, and a short explanation of why raw BM25 and cosine-similarity scores are not added directly.

Illinois Chat may provide conceptual or procedural hints for this question, but it must not provide a completed implementation, a worked final answer, or a substitute submission.

## Question 3: Failure Analysis

Describe one query for which lexical retrieval is likely to outperform dense retrieval and one query for which dense retrieval is likely to outperform lexical retrieval. Justify both choices without using private course data.
