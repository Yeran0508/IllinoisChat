# V1 real-LLM smoke test — 2026-11-10

## Why this test exists

Unit and integration tests prove deterministic application behavior, but they cannot prove that a real local model follows the structured-output contracts or completes within the configured timeout. This smoke test checks that boundary without turning one model run into a general quality claim.

## Environment and procedure

- Application: local Docker Compose stack from the current uncommitted V1 workspace after commit `980bc2d`
- Provider: local Ollama through its OpenAI-compatible `/v1/chat/completions` endpoint
- Models tried: `llama3.2:3b` and `qwen3:4b`
- Qwen request configuration: temperature 0, JSON response format, `reasoning_effort=none`, 60-second application timeout
- Corpus: `data/sample/m2-retrieval-notes.md` plus the protected `data/sample/m3-protected-homework.md`
- Raw summary: `docs/experiments/results/v1-real-llm-smoke.json`

The ordinary question, unsupported question, and protected-assignment request were sent through `POST /api/v1/chat`. The frontend proxy health route was also called through port 4173.

## Results

`llama3.2:3b` reached the application but over-refused ordinary answerable questions because its evidence-sufficiency decision remained false. The simple RRF request took about 11.8 seconds and ended with `iterative_evidence_insufficient`; the out-of-domain request correctly refused, and the protected-assignment path correctly returned a bounded hint.

`qwen3:4b` did not pass the ordinary-answer smoke test. Its decomposition request returned Ollama HTTP 500 with `prediction aborted, token repeat limit reached`; a second compatibility probe using `think=false` plus `/no_think` timed out after 90 seconds. The API correctly converted the provider failure into HTTP 503 rather than returning an unsupported answer. The protected-assignment path still passed because protection runs before generation: it returned `homework_hint`, hint level 1, in 300 ms. The frontend reverse proxy health request returned HTTP 200.

## Conclusion and evidence boundary

The real-provider failure behavior and the protected-assignment path are verified. Grounded generation with the currently installed small Ollama models is **not** verified, so this project must not claim real-model answer quality, real-model end-to-end latency, token cost, or a successful held-out evaluation yet. The deterministic automated suite remains the release gate for application logic; a future model-runtime qualification should pin the Ollama version, model digest, context settings, and a held-out dataset before changing this conclusion.
