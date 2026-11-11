import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  askQuestion,
  ChatResponse,
  fetchMetrics,
  CacheMetrics,
  uploadAndIngest,
} from "./api";

const EXAMPLE_QUESTIONS = [
  "How does reciprocal rank fusion combine BM25 and vector rankings?",
  "Why do immutable document versions help evaluation and cache invalidation?",
  "Who won the 2026 World Series?",
];

function sourceLocation(page: number | null, section: string | null): string {
  if (page !== null) return `Page ${page}`;
  return section || "Source excerpt";
}

function statusCopy(result: ChatResponse): { label: string; tone: string; description: string } {
  if (result.status === "homework_hint") {
    return {
      label: `Protected assignment · Hint level ${result.hint_level ?? 1}`,
      tone: "amber",
      description: "The system recognized protected coursework and limited the response to study guidance.",
    };
  }
  if (result.status !== "answered") {
    return {
      label: "Insufficient evidence",
      tone: "slate",
      description: "The indexed course materials did not provide enough support for a grounded answer.",
    };
  }
  return {
    label: result.cache_hit ? "Grounded answer · Cache hit" : "Grounded answer · Fresh",
    tone: "green",
    description: "Every answer sentence is linked to evidence retrieved from the indexed course corpus.",
  };
}

function MetricCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <article className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function App() {
  const [courseCode, setCourseCode] = useState("CS-RAG");
  const [query, setQuery] = useState(EXAMPLE_QUESTIONS[0]);
  const [result, setResult] = useState<ChatResponse | null>(null);
  const [metrics, setMetrics] = useState<CacheMetrics | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [adminOpen, setAdminOpen] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);

  const refreshMetrics = () => {
    fetchMetrics().then(setMetrics).catch(() => setMetrics(null));
  };

  useEffect(refreshMetrics, []);

  async function submitQuestion(event: FormEvent) {
    event.preventDefault();
    if (!query.trim() || !courseCode.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const response = await askQuestion(courseCode.trim(), query.trim());
      setResult(response);
      refreshMetrics();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to reach Illinois Chat.");
    } finally {
      setLoading(false);
    }
  }

  async function submitDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setUploadStatus("Registering document…");
    const form = new FormData(event.currentTarget);
    try {
      const registered = await uploadAndIngest(form);
      setUploadStatus(
        registered.reused
          ? `Existing version reused (${registered.version_id.slice(0, 8)}…).`
          : `Document registered and ingestion queued (${registered.version_id.slice(0, 8)}…).`,
      );
      event.currentTarget.reset();
    } catch (requestError) {
      setUploadStatus(requestError instanceof Error ? requestError.message : "Document upload failed.");
    }
  }

  const answerStatus = useMemo(() => (result ? statusCopy(result) : null), [result]);

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="Illinois Chat home">
          <span className="brand-mark">I</span>
          <span>
            <strong>Illinois Chat</strong>
            <small>Evidence, not guesswork</small>
          </span>
        </a>
        <nav aria-label="Primary navigation">
          <a href="#ask">Ask</a>
          <a href="#evidence">Evidence</a>
          <button className="nav-button" type="button" onClick={() => setAdminOpen((value) => !value)}>
            {adminOpen ? "Close admin" : "Course admin"}
          </button>
        </nav>
      </header>

      <main id="top">
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero-copy">
            <p className="eyebrow">Grounded campus intelligence</p>
            <h1 id="hero-title">Ask your course materials.<br /><em>Inspect the proof.</em></h1>
            <p className="hero-subtitle">
              Hybrid retrieval, sentence-level citations, assignment-safe hints, and explicit refusal when the evidence runs out.
            </p>
            <div className="trust-row" aria-label="System guarantees">
              <span>BM25 + vectors</span><span>Verified citations</span><span>Bounded retrieval</span>
            </div>
          </div>
          <aside className="hero-note">
            <span className="note-index">01</span>
            <p>Designed for the moment after “where was that in the notes?” and before an unsupported model answer.</p>
          </aside>
        </section>

        <section className="workspace" id="ask">
          <div className="workspace-heading">
            <div><p className="eyebrow dark">Student workspace</p><h2>Ask with a source boundary.</h2></div>
            <label className="course-field">Course <input value={courseCode} onChange={(event) => setCourseCode(event.target.value)} aria-label="Course code" /></label>
          </div>

          <form className="question-form" onSubmit={submitQuestion}>
            <label htmlFor="question">Question</label>
            <div className="question-box">
              <textarea id="question" value={query} onChange={(event) => setQuery(event.target.value)} rows={3} maxLength={4000} />
              <button type="submit" disabled={loading}>{loading ? "Tracing evidence…" : "Ask Illinois Chat"}<span aria-hidden="true">↗</span></button>
            </div>
            <div className="examples">
              <span>Try:</span>
              {EXAMPLE_QUESTIONS.map((question) => <button type="button" key={question} onClick={() => setQuery(question)}>{question}</button>)}
            </div>
          </form>

          {error && <div className="error-banner" role="alert"><strong>Request failed.</strong> {error}</div>}

          {result && answerStatus && (
            <div className="result-grid" id="evidence">
              <article className="answer-panel">
                <div className="panel-kicker"><span className={`status-dot ${answerStatus.tone}`} />{answerStatus.label}</div>
                <h3>{result.status === "answered" ? "Answer" : result.status === "homework_hint" ? "Study guidance" : "Why I stopped"}</h3>
                <p className="status-description">{answerStatus.description}</p>
                <div className="answer-text">
                  {result.sentences.length > 0 ? result.sentences.map((sentence, index) => (
                    <p key={`${sentence.text}-${index}`}>{sentence.text} {sentence.citation_ids.map((id) => <a key={id} href={`#citation-${id}`} className="citation-link">[{id}]</a>)}</p>
                  )) : <p>{result.answer || `Reason: ${result.refusal_reason?.replaceAll("_", " ") ?? "insufficient evidence"}.`}</p>}
                </div>
                <footer className="answer-meta">
                  <span>{result.latency_ms} ms</span><span>{result.model_name}</span><span>Request {result.request_id.slice(0, 8)}</span>
                  {result.cache_similarity !== null && <span>{(result.cache_similarity * 100).toFixed(1)}% cache similarity</span>}
                </footer>
              </article>

              <aside className="evidence-panel">
                <div className="panel-title"><div><p className="eyebrow dark">Source ledger</p><h3>{result.citations.length} verified citation{result.citations.length === 1 ? "" : "s"}</h3></div><span className="verified-seal">✓</span></div>
                <div className="citation-list">
                  {result.citations.length === 0 && <p className="empty-state">No source was presented because the response did not pass the grounded-answer path.</p>}
                  {result.citations.map((citation) => (
                    <article className="citation-card" id={`citation-${citation.citation_id}`} key={citation.citation_id}>
                      <div><span className="citation-number">{String(citation.citation_id).padStart(2, "0")}</span><span className="score">{Math.round(citation.score * 100)}% relevance</span></div>
                      <h4>{citation.title}</h4><p className="source-path">{citation.source_name} · {sourceLocation(citation.page_number, citation.section_path)}</p>
                      <blockquote>{citation.evidence}</blockquote>
                    </article>
                  ))}
                </div>
              </aside>
            </div>
          )}
        </section>

        {result?.retrieval_trace && (
          <section className="trace-section" aria-labelledby="trace-title">
            <div><p className="eyebrow">Retrieval trace</p><h2 id="trace-title">A bounded path to the answer.</h2></div>
            <div className="trace-flow">
              {result.retrieval_trace.subquestions.map((subquestion, index) => (
                <article key={subquestion}><span>{String(index + 1).padStart(2, "0")}</span><p>{subquestion}</p></article>
              ))}
              <article className="trace-stop"><span>→</span><p>{result.retrieval_trace.stopped_reason.replaceAll("_", " ")} · {result.retrieval_trace.steps_used} step{result.retrieval_trace.steps_used === 1 ? "" : "s"}</p></article>
            </div>
          </section>
        )}

        <section className="observability" aria-labelledby="metrics-title">
          <div><p className="eyebrow dark">Operational evidence</p><h2 id="metrics-title">The cache reports what it actually observed.</h2></div>
          <div className="metric-grid">
            <MetricCard label="Cache hit rate" value={metrics ? `${(metrics.hit_rate * 100).toFixed(1)}%` : "—"} detail="Observed requests only" />
            <MetricCard label="Lookup P95" value={metrics ? `${metrics.latency_ms.p95.toFixed(0)} ms` : "—"} detail="Bounded recent sample" />
            <MetricCard label="Stale answers" value={metrics ? `${(metrics.stale_answer_rate * 100).toFixed(1)}%` : "—"} detail={`${metrics?.stale_rejections ?? 0} incompatible entries rejected`} />
          </div>
        </section>

        {adminOpen && (
          <section className="admin-section" aria-labelledby="admin-title">
            <div><p className="eyebrow">Course administration</p><h2 id="admin-title">Register a source, then queue ingestion.</h2><p>PDF, Markdown, and UTF-8 text are accepted. Protected sources remain isolated from the normal answer index.</p></div>
            <form onSubmit={submitDocument}>
              <label>Course code<input name="course_code" defaultValue={courseCode} required /></label>
              <label>Course name<input name="course_name" defaultValue="Retrieval-Augmented Generation" required /></label>
              <label>Document title<input name="title" placeholder="Week 4 retrieval notes" required /></label>
              <label className="file-field">Source file<input name="file" type="file" accept=".pdf,.md,.txt,text/plain,text/markdown,application/pdf" required /></label>
              <label className="check-field"><input name="is_protected" type="checkbox" value="true" />This is protected assignment material</label>
              <button type="submit">Register and ingest</button>
              {uploadStatus && <p className="upload-status" role="status">{uploadStatus}</p>}
            </form>
          </section>
        )}
      </main>

      <footer className="site-footer"><span>Illinois Chat · V1 interview build</span><span>Grounded by design. Measured with limits.</span></footer>
    </div>
  );
}

export default App;
