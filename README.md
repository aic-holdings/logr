# Logr

**A giant catch-all giving AI a chance to study success and failure.**

Centralized structured logging service with OpenTelemetry compatibility, LLM-native fields, semantic search, and anomaly detection.

## Why Logr?

- **AI-First**: First-class support for LLM operations (model, tokens, cost, prompts)
- **OpenTelemetry Compatible**: Trace IDs, span hierarchy, distributed tracing
- **Semantic Search**: Find logs by meaning with pgvector embeddings
- **Event Payloads**: Separate large payloads (prompts, completions) per OTEL LLM Working Group recommendation
- **Anomaly Detection**: Automatic error spikes, latency anomalies, new error types

## Quick Start

### Python Client

```python
from logr_client import Logr

logr = Logr(
    api_key="logr_xxx",
    service="my-service",
    version="1.0.0",
)

# Simple logging
logr.info("User logged in", user_id="U123")
logr.error("Database timeout", error_type="TimeoutError", duration_ms=30000)

# LLM operation with full context
logr.llm(
    message="Completion successful",
    model="claude-3-opus",
    tokens_in=500,
    tokens_out=1200,
    cost_usd=0.045,
    duration_ms=3500,
    prompt="What is the weather?",
    completion="I don't have access to real-time weather...",
    system_prompt="You are a helpful assistant.",
)

# Distributed tracing
with logr.trace("process_request") as trace:
    logr.info("Fetching data", trace_id=trace.trace_id)
    # ... do work ...
    logr.info("Done", trace_id=trace.trace_id, duration_ms=150)
```

### Direct API

```bash
# Simple log
curl -X POST https://logr.jettaintelligence.com/v1/logs \
  -H "Authorization: Bearer logr_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "service": "my-service",
    "level": "info",
    "message": "User logged in",
    "user_id": "U123"
  }'

# LLM operation with events
curl -X POST https://logr.jettaintelligence.com/v1/logs \
  -H "Authorization: Bearer logr_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "service": "chatbot",
    "level": "info",
    "message": "LLM completion",
    "model": "claude-3-opus",
    "tokens_in": 500,
    "tokens_out": 1200,
    "cost_usd": 0.045,
    "duration_ms": 3500,
    "events": [
      {"event_type": "system_prompt", "content": "You are helpful..."},
      {"event_type": "prompt", "content": "What is the weather?", "sequence": 1},
      {"event_type": "completion", "content": "I cannot access...", "sequence": 2}
    ]
  }'
```

## API Reference

### Logs

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/logs` | POST | Submit a single log entry |
| `/v1/logs/batch` | POST | Submit up to 1000 logs |
| `/v1/logs` | GET | Query logs with filters |
| `/v1/logs/{id}` | GET | Get specific log with events |
| `/v1/logs/trace/{trace_id}` | GET | Get all logs for a trace |
| `/v1/logs/services` | GET | List all services |
| `/v1/logs/models` | GET | List all LLM models |
| `/v1/logs/stats` | GET | Get statistics |

### Spans (Distributed Tracing)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/spans` | POST | Create a span |
| `/v1/spans/batch` | POST | Submit multiple spans |
| `/v1/spans` | GET | Query spans |
| `/v1/spans/trace/{trace_id}` | GET | Get trace with span tree |

### Search & Analysis

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/search/semantic` | POST | Semantic search using embeddings |
| `/v1/search/similar` | POST | Find similar logs |
| `/v1/search/errors/grouped` | GET | Group errors by type |
| `/v1/search/anomalies` | GET | Detect anomalies |

## Log Entry Schema

```json
{
  // Required
  "service": "taskr-bot",
  "level": "info|debug|warn|error|fatal",
  "message": "User request processed",

  // Context
  "context": {"key": "value"},
  "environment": "production",
  "host": "container-abc",
  "version": "1.2.0",

  // Trace Correlation (OpenTelemetry)
  "trace_id": "abc123",
  "span_id": "span_001",
  "parent_span_id": "span_000",

  // Request Context
  "request_id": "req_xyz",
  "user_id": "U123",
  "session_id": "sess_456",

  // Timing
  "timestamp": "2026-01-31T20:00:00Z",
  "duration_ms": 145.5,

  // LLM-Specific
  "model": "claude-3-opus",
  "tokens_in": 500,
  "tokens_out": 1200,
  "cost_usd": 0.045,

  // Error Details
  "error_type": "TimeoutError",
  "error_message": "Connection timed out",
  "stack_trace": "...",

  // Events (large payloads)
  "events": [
    {
      "event_type": "prompt|completion|tool_call|system_prompt|retrieval",
      "content": "...",
      "sequence": 0
    }
  ]
}
```

## Query Examples

```bash
# All errors from taskr-bot
GET /v1/logs?service=taskr-bot&level=error

# Trace a request across services
GET /v1/logs?trace_id=abc123

# Slow Claude operations
GET /v1/logs?model=claude-3-opus&min_duration_ms=5000

# Recent errors with stack traces
GET /v1/logs?has_error=true&since=2026-01-31T00:00:00Z

# Full trace with events
GET /v1/logs/trace/abc123

# Semantic search
POST /v1/search/semantic
{"query": "database connection timeout"}

# Find similar errors
POST /v1/search/similar
{"log_id": "uuid-here"}

# Detect anomalies
GET /v1/search/anomalies?hours=24
```

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                        ALL SERVICES                            │
│  taskr-bot │ sable-bot │ artemis │ forge │ watts │ jetta-sso  │
└──────┬─────────┬──────────┬─────────┬───────┬────────┬────────┘
       │         │          │         │       │        │
       └─────────┴──────────┴────┬────┴───────┴────────┘
                                 ▼
                    ┌────────────────────────┐
                    │         logr           │
                    │   FastAPI + asyncpg    │
                    │                        │
                    │  POST /v1/logs         │
                    │  POST /v1/spans        │
                    │  GET  /v1/search/*     │
                    └───────────┬────────────┘
                                │
                    ┌───────────▼────────────┐
                    │   Postgres + pgvector  │
                    │   (dedicated Railway)  │
                    │                        │
                    │  - log_entries         │
                    │  - log_events          │
                    │  - spans               │
                    │  - embeddings          │
                    └────────────────────────┘
                                │
                    ┌───────────▼────────────┐
                    │     AI Analysis        │
                    │  "Why did X fail?"     │
                    │  "Pattern in errors?"  │
                    │  "Similar past issue?" │
                    └────────────────────────┘
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `MASTER_API_KEY` | Admin operations key | Yes |
| `ARTEMIS_API_KEY` | For embedding generation | No |
| `ARTEMIS_URL` | Artemis API URL | No |
| `LOG_RETENTION_DAYS` | Auto-delete after N days (default: 90) | No |

## Database Schema

### log_entries
Primary log storage with indexed fields for fast queries.

### log_events
Large payloads (prompts, completions, tool calls) stored separately per OpenTelemetry LLM Working Group recommendation.

### spans
OpenTelemetry-compatible distributed tracing spans.

## Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Run locally
DATABASE_URL=postgresql://... uvicorn app.main:app --reload

# Run tests
pytest

# Lint
ruff check app
```

## Deployment

Deploy to Railway with a dedicated Postgres database:

```bash
railway init
railway add --database postgres
railway up
```

Set environment variables:
- `DATABASE_URL` (auto-set by Railway)
- `MASTER_API_KEY` (generate a secure key)

## License

MIT
