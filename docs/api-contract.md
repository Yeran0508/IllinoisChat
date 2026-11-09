# Illinois Chat API Contract

This document records only endpoints whose contract has been introduced in the implementation.

## `GET /api/v1/health`

Confirms that the API process and HTTP routing are available. It is a liveness endpoint and does not claim that PostgreSQL, OpenSearch, Redis, or external model providers are ready.

### Response: `200 OK`

```json
{
  "status": "ok",
  "service": "Illinois Chat API",
  "version": "0.1.0",
  "environment": "development"
}
```
