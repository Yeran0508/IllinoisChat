export type Citation = {
  citation_id: number;
  chunk_id: string;
  document_id: string;
  version_id: string;
  title: string;
  source_name: string;
  page_number: number | null;
  section_path: string | null;
  evidence: string;
  score: number;
};

export type AnswerSentence = {
  text: string;
  citation_ids: number[];
};

export type RetrievalAttempt = {
  step: number;
  query: string;
  chunk_ids: string[];
};

export type RetrievalTrace = {
  original_query: string;
  subquestions: string[];
  attempts: RetrievalAttempt[];
  sufficient: boolean;
  missing_subquestions: string[];
  steps_used: number;
  stopped_reason: string;
};

export type ChatResponse = {
  request_id: string;
  status: string;
  answer: string | null;
  sentences: AnswerSentence[];
  citations: Citation[];
  refusal_reason: string | null;
  model_name: string;
  latency_ms: number;
  safety_mode: string;
  hint_level: number | null;
  protected_match_score: number | null;
  retrieval_trace: RetrievalTrace | null;
  cache_hit: boolean;
  cache_similarity: number | null;
};

export type CacheMetrics = {
  hits?: number;
  misses?: number;
  stale_rejections?: number;
  hit_rate: number;
  stale_answer_rate: number;
  latency_ms: { mean: number; p50: number; p95: number };
};

type MetricsResponse = { semantic_cache: CacheMetrics };

export type RegistrationResponse = {
  document_id: string;
  version_id: string;
  status: string;
  reused: boolean;
};

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Preserve the status-based message for a non-JSON response.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export function askQuestion(courseCode: string, query: string): Promise<ChatResponse> {
  return request<ChatResponse>("/api/v1/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ course_code: courseCode, query }),
  });
}

export async function fetchMetrics(): Promise<CacheMetrics> {
  return (await request<MetricsResponse>("/api/v1/metrics")).semantic_cache;
}

export async function uploadAndIngest(form: FormData): Promise<RegistrationResponse> {
  const registration = await request<RegistrationResponse>("/api/v1/documents", {
    method: "POST",
    body: form,
  });
  await request(`/api/v1/documents/${registration.document_id}/ingest?version_id=${registration.version_id}`, {
    method: "POST",
  });
  return registration;
}
