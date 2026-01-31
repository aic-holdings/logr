# Logr

Centralized structured logging service for AI-powered log analysis.

## Philosophy

**A giant catch-all giving AI a chance to study success and failure.**

All services emit structured logs to Logr, creating a corpus for:
- Debugging across services
- Pattern recognition in failures
- AI-powered root cause analysis
- Historical audit trails

## Quick Start

### Sending Logs

```python
import httpx

LOGR_URL = "https://logr.jettaintelligence.com"
LOGR_API_KEY = "logr_..."

def log(level: str, message: str, **context):
    httpx.post(
        f"{LOGR_URL}/v1/logs",
        headers={"Authorization": f"Bearer {LOGR_API_KEY}"},
        json={
            "service": "my-service",
            "level": level,
            "message": message,
            "context": context,
        }
    )

# Usage
log("info", "User logged in", user_id="U123", method="sso")
log("error", "Database timeout", query="SELECT...", latency_ms=30000)
```

### Batch Logging

```python
httpx.post(
    f"{LOGR_URL}/v1/logs/batch",
    headers={"Authorization": f"Bearer {LOGR_API_KEY}"},
    json={
        "logs": [
            {"service": "my-service", "level": "info", "message": "Event 1"},
            {"service": "my-service", "level": "info", "message": "Event 2"},
        ]
    }
)
```

### Querying Logs

```bash
# All errors from taskr-bot in the last hour
curl -H "Authorization: Bearer $LOGR_API_KEY" \
  "$LOGR_URL/v1/logs?service=taskr-bot&level=error&since=2026-01-31T19:00:00Z"

# Trace a request across services
curl -H "Authorization: Bearer $LOGR_API_KEY" \
  "$LOGR_URL/v1/logs?trace_id=trace_abc123"

# Search for timeouts
curl -H "Authorization: Bearer $LOGR_API_KEY" \
  "$LOGR_URL/v1/logs?search=timeout"
```

## API Reference

### POST /v1/logs

Submit a single log entry.

```json
{
    "service": "taskr-bot",
    "level": "error",
    "message": "Artemis timeout after 30s",
    "context": {
        "latency_ms": 30000,
        "model": "claude-3-opus"
    },
    "trace_id": "trace_abc123",
    "request_id": "req_xyz",
    "user_id": "U123",
    "timestamp": "2026-01-31T20:30:00Z",
    "environment": "production"
}
```

### POST /v1/logs/batch

Submit up to 1000 logs in a single request.

### GET /v1/logs

Query logs with filters:
- `service` - Filter by service name
- `level` - Filter by log level (debug/info/warn/error/fatal)
- `environment` - Filter by environment
- `trace_id` - Cross-service correlation
- `request_id` - Single request tracking
- `user_id` - User attribution
- `since` / `until` - Time range
- `search` - Full-text search in message
- `page` / `page_size` - Pagination

### GET /v1/logs/stats

Get statistics for a time window.

### GET /v1/logs/services

List all services that have submitted logs.

## Log Levels

| Level | Usage |
|-------|-------|
| `debug` | Detailed debugging info |
| `info` | Normal operations |
| `warn` | Something unexpected but handled |
| `error` | Operation failed |
| `fatal` | Service crash/restart |

## Correlation IDs

Use `trace_id` to correlate logs across services:

```
User Request → API Gateway → taskr-bot → Artemis
     │              │             │          │
     └──────────────┴─────────────┴──────────┘
                 trace_id: "trace_abc123"
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection | Yes |
| `MASTER_API_KEY` | Admin operations | Yes |

## Architecture

```
┌──────────────────────────────────────────────────┐
│              All Services                        │
│  taskr-bot │ sable-bot │ artemis │ forge │ ...  │
└──────┬─────────┬──────────┬─────────┬───────────┘
       │         │          │         │
       └─────────┴──────────┴────┬────┘
                                 ▼
                    ┌────────────────────────┐
                    │         logr           │
                    │   FastAPI + asyncpg    │
                    └───────────┬────────────┘
                                │
                    ┌───────────▼────────────┐
                    │   Postgres + pgvector  │
                    │   (dedicated Railway)  │
                    └────────────────────────┘
```

## Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Run locally
DATABASE_URL=postgresql://... uvicorn app.main:app --reload

# Run tests
pytest
```

## License

MIT
