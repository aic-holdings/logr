# Logr — Centralized Structured Logging

Thin FastAPI service + Railway Postgres. Any AIC app writes structured logs via HTTP POST.

**Status: DEPLOYED AND RUNNING** (since 2026-01-31)

## Architecture

```
logr/
  __init__.py      — package root
  api.py           — FastAPI app with full observability API
  db.py            — Postgres connection pool (psycopg) + schema auto-apply
  models.py        — Pydantic request/response models
tests/
  test_api.py      — API tests
```

## Key Rules

- Schema auto-applied on startup (CREATE IF NOT EXISTS)
- Soft deletes only (deleted_at column, never hard DELETE)
- All logs are append-only — no updates to existing entries
- Callers should use short timeouts (5s) — logging must never block the caller
- Private Railway networking: apps reach logr via `logr-api.railway.internal`
- Public domain: `logr.jettaintelligence.com` (TLS cert may need provisioning)
- Railway-provided domain: `logr-api-production.up.railway.app` (always works)

## Authentication

Bearer token auth on all endpoints except `/health`:
```
Authorization: Bearer logr_xxx
```

Admin endpoints (`/v1/admin/*`) require master API key.
Service accounts can be created for per-app auth.

## Railway

**Project:** logr (ID: `1f655d6d-d70a-4ba1-9cca-a36b4cf4319b`)
**Services:**
- pgvector (Postgres, ID: `59bbf3b1-6029-4825-bcdf-cccfec40c927`)
- logr-api (ID: `9b31610b-3b2c-4e32-a108-8a9f9b10524f`)

**Environment variables (logr-api):**
- `DATABASE_URL` — Railway Postgres (private networking: `pgvector.railway.internal:5432`)
- `MASTER_API_KEY` — `logr_master_44e83d85297789c46aa3f5d7d78c3b782fb830833180d3ed`
- `PORT` — 8000

**Networking:**
- Private: `logr-api.railway.internal` (bot-farm and other Railway services use this)
- Public: `logr.jettaintelligence.com` (custom domain, TLS may need setup)
- Railway default: `logr-api-production.up.railway.app` (always accessible)

**TCP Proxy (cross-project + local access):**
- `shuttle.proxy.rlwy.net:45970` → port 5432
- Use `sslmode=disable` (Railway TCP proxy doesn't terminate SSL)
- Connection string: `postgresql://postgres:<password>@shuttle.proxy.rlwy.net:45970/railway?sslmode=disable`
- Used by `aic-logging` package in bot-farm (via `LOG_DB_URL` env var)

## API Endpoints

### Logs (core)
```
POST /v1/logs                    — Create single log entry
POST /v1/logs/batch              — Create up to 1000 log entries
GET  /v1/logs                    — List logs (with filters)
GET  /v1/logs/{log_id}           — Get single log
GET  /v1/logs/trace/{trace_id}   — Get all logs for a trace
GET  /v1/logs/services           — List known services
GET  /v1/logs/models             — List LLM models seen
GET  /v1/logs/stats              — Get log statistics
```

### Spans (distributed tracing)
```
POST /v1/spans                   — Create span
POST /v1/spans/batch             — Create span batch
GET  /v1/spans                   — List spans
GET  /v1/spans/trace/{trace_id}  — Get all spans for a trace
```

### Search
```
POST /v1/search/semantic         — Semantic search (natural language)
POST /v1/search/similar          — Find similar logs
GET  /v1/search/anomalies        — Detect anomalies
GET  /v1/search/errors/grouped   — Get grouped errors
```

### Admin
```
POST /v1/admin/service-accounts  — Create service account
GET  /v1/admin/service-accounts  — List service accounts
POST /v1/admin/keys              — Issue API key
GET  /v1/admin/keys              — List API keys
DELETE /v1/admin/keys/{key_id}   — Revoke key
GET  /v1/admin/stats             — Admin stats
POST /v1/admin/retention/cleanup — Run retention cleanup
GET  /v1/admin/retention/stats   — Retention stats
```

### Infrastructure
```
GET  /health                     — Health check (no auth)
GET  /metrics                    — Internal metrics
GET  /metrics/prometheus          — Prometheus metrics
```

## Log Entry Schema (POST /v1/logs)

Required fields: `service`, `level`, `message`

```json
{
  "service": "bot-farm",
  "level": "info",
  "message": "User asked about Wrike tasks",
  "context": {"channel": "C123", "user_id": "U456", "thread_ts": "123.456"},
  "trace_id": "abc-123",
  "user_id": "U456",
  "session_id": "thread-123.456",
  "duration_ms": 1500,
  "model": "anthropic/claude-haiku-4.5",
  "tokens_in": 800,
  "tokens_out": 200,
  "cost_usd": 0.003,
  "events": [
    {
      "event_type": "system_prompt",
      "content": "You are Wrike Bot...",
      "sequence": 0
    },
    {
      "event_type": "prompt",
      "content": "Show my tasks",
      "sequence": 1
    },
    {
      "event_type": "tool_call",
      "content": "search_tasks",
      "metadata": {"args": {"query": "assignee:me"}},
      "sequence": 2,
      "duration_ms": 450
    },
    {
      "event_type": "tool_result",
      "content": "[{\"id\": \"...\", \"title\": \"Fix bug\"}]",
      "metadata": {"tool_name": "search_tasks"},
      "sequence": 3
    },
    {
      "event_type": "completion",
      "content": "Here are your tasks: ...",
      "sequence": 4
    }
  ]
}
```

### Event Types

| Type | Description |
|------|-------------|
| `system_prompt` | System prompt sent to LLM |
| `prompt` | User message / input |
| `completion` | LLM response / output |
| `tool_call` | Tool invocation (name in content, args in metadata) |
| `tool_result` | Tool result (result in content, tool_name in metadata) |
| `retrieval` | RAG/document retrieval |
| `context` | Additional context injected |

## Features

- **LLM Tracking**: First-class `model`, `tokens_in`, `tokens_out`, `cost_usd` fields
- **Distributed Tracing**: W3C trace_id/span_id for cross-service correlation
- **Semantic Search**: Natural language log search (pgvector + embeddings)
- **Anomaly Detection**: Automatic pattern and spike detection
- **Retention**: 90-day default, configurable cleanup
- **Service Accounts**: Per-app auth with read/write permissions

## Scope and Limitations

Logr is an **LLM-first observability platform**, not a full-stack APM.

**What it covers well:**
- Structured logging for any AIC service (via `service` field + `context` JSONB)
- LLM conversation tracing (prompts, completions, tool calls, tokens, cost)
- Cross-service correlation via W3C trace_id/span_id
- Log search, anomaly detection, error grouping

**What it does NOT cover (would need separate tools):**
- Infrastructure metrics (CPU, memory, disk) — use Prometheus/Grafana or Railway metrics
- HTTP request/response APM (latency percentiles, throughput) — use traditional APM
- Alerting/paging — no built-in notification system
- Real-time dashboards — query API exists but no UI layer

**Design intent:** Any AIC app can write here. LLM-specific fields are optional — a non-LLM service can use `service`, `level`, `message`, `context`, and `trace_id` for standard structured logging. The LLM fields (`model`, `tokens_in`, `tokens_out`, `cost_usd`, event types like `prompt`/`completion`) add value when present but don't gate usage.

## Integration with Bot-Farm

Bot-farm should create a LogrClient that:
1. Creates a log entry per conversation (`trace_id` = conversation thread)
2. Attaches events for each lifecycle step (prompt, tool_call, tool_result, completion)
3. Includes LLM metadata (model, tokens, cost)
4. Uses `logr-api.railway.internal` for private networking (sub-1ms)
5. Swallows errors — logging must never break the bot

Example integration:
```python
import httpx

client = httpx.Client(
    base_url="http://logr-api.railway.internal:8000",
    headers={"Authorization": "Bearer logr_xxx"},
    timeout=5.0,
)

client.post("/v1/logs", json={
    "service": "bot-farm",
    "level": "info",
    "message": "Conversation with Wrike Bot",
    "trace_id": conversation_id,
    "user_id": slack_user_id,
    "model": "anthropic/claude-haiku-4.5",
    "tokens_in": 800,
    "tokens_out": 200,
    "events": [...]
})
```
