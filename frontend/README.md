# Illinois Chat frontend

Interview-oriented React client for the Illinois Chat API. It demonstrates grounded answers, citations, refusal and homework-hint states, retrieval traces, semantic-cache metadata, document ingestion, and cache metrics.

```bash
npm ci
npm run dev
```

The development server proxies `/api` to `http://localhost:8000`. Override the production API base URL at build time with `VITE_API_BASE_URL`.

```bash
npm run typecheck
npm test -- --run
npm run build
```
