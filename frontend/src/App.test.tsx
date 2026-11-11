import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import App from "./App";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test("renders a grounded answer, citation, trace, and cache metadata", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith("/api/v1/metrics")) {
      return new Response(JSON.stringify({ semantic_cache: { hit_rate: 0.5, stale_answer_rate: 0, stale_rejections: 1, latency_ms: { mean: 4, p50: 3, p95: 7 } } }), { status: 200 });
    }
    return new Response(JSON.stringify({
      request_id: "12345678-0000-0000-0000-000000000000",
      status: "answered",
      answer: "RRF combines ranks.",
      sentences: [{ text: "RRF combines ranks.", citation_ids: [1] }],
      citations: [{ citation_id: 1, chunk_id: "1", document_id: "2", version_id: "3", title: "Retrieval notes", source_name: "notes.md", page_number: null, section_path: "RRF", evidence: "Each list contributes reciprocal rank.", score: 0.91 }],
      refusal_reason: null,
      model_name: "test-model",
      latency_ms: 12,
      safety_mode: "standard",
      hint_level: null,
      protected_match_score: null,
      retrieval_trace: { original_query: "RRF", subquestions: ["How are ranks fused?"], attempts: [], sufficient: true, missing_subquestions: [], steps_used: 1, stopped_reason: "sufficient" },
      cache_hit: true,
      cache_similarity: 0.98,
    }), { status: 200 });
  });

  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: /ask illinois chat/i }));

  expect(await screen.findByText("RRF combines ranks.")).toBeInTheDocument();
  expect(screen.getByText("Retrieval notes")).toBeInTheDocument();
  expect(screen.getByText(/grounded answer · cache hit/i)).toBeInTheDocument();
  expect(screen.getByText("How are ranks fused?")).toBeInTheDocument();
  await waitFor(() => expect(fetchMock).toHaveBeenCalled());
});

test("shows a protected-assignment hint without pretending it is a normal answer", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    if (String(input).endsWith("/api/v1/metrics")) return new Response("unavailable", { status: 503 });
    return new Response(JSON.stringify({
      request_id: "12345678-0000-0000-0000-000000000000",
      status: "homework_hint",
      answer: "Review reciprocal rank contributions before implementing the merge.",
      sentences: [], citations: [], refusal_reason: null, model_name: "safety-policy", latency_ms: 4,
      safety_mode: "protected_assignment", hint_level: 1, protected_match_score: 0.94,
      retrieval_trace: null, cache_hit: false, cache_similarity: null,
    }), { status: 200 });
  });

  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: /ask illinois chat/i }));

  expect(await screen.findByText(/protected assignment · hint level 1/i)).toBeInTheDocument();
  expect(screen.getByText(/review reciprocal rank contributions/i)).toBeInTheDocument();
});
