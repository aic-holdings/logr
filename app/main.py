"""Logr - Centralized structured logging service for AI-powered analysis."""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import text

from app.config import settings
from app.database import init_db, async_session_maker
from app.routers import logs, spans, search, admin
from app.middleware import (
    RateLimitMiddleware,
    RequestSizeLimitMiddleware,
    MetricsMiddleware,
)
from app.embeddings import pipeline as embedding_pipeline

# Global metrics instance
metrics_middleware = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup, start background tasks."""
    await init_db()
    # Start embedding pipeline as background task
    task = asyncio.create_task(embedding_pipeline.start())
    yield
    # Stop embedding pipeline on shutdown
    embedding_pipeline.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Logr",
    description="""
# Logr - Centralized Structured Logging

A giant catch-all giving AI a chance to study success and failure.

## Features

- **Structured Logging**: JSON logs with rich context
- **Distributed Tracing**: OpenTelemetry-compatible spans
- **LLM Tracking**: First-class support for AI operations (tokens, cost, model)
- **Semantic Search**: Find logs by meaning, not just keywords
- **Anomaly Detection**: Automatic pattern and spike detection
- **Event Payloads**: Separate storage for prompts, completions, tool calls

## Authentication

All endpoints require a Bearer token:
```
Authorization: Bearer logr_xxx
```

## Quick Start

```python
import httpx

# Simple log
httpx.post(
    "https://logr.jettaintelligence.com/v1/logs",
    headers={"Authorization": "Bearer logr_xxx"},
    json={
        "service": "my-service",
        "level": "info",
        "message": "User logged in",
        "user_id": "U123"
    }
)
```
    """,
    version=settings.VERSION,
    lifespan=lifespan,
)

# Add middleware (order matters - first added = outermost)
metrics_middleware = MetricsMiddleware(app)
app.add_middleware(MetricsMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_minute=1000)
app.add_middleware(RequestSizeLimitMiddleware, max_size_mb=10)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(logs.router)
app.include_router(spans.router)
app.include_router(search.router)
app.include_router(admin.router)


@app.get("/health")
async def health():
    """
    Health check endpoint with database connectivity test.

    Returns service status and feature availability.
    """
    db_healthy = False
    db_error = None

    try:
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
            db_healthy = True
    except Exception as e:
        db_error = str(e)

    status = "healthy" if db_healthy else "degraded"

    return {
        "status": status,
        "service": settings.SERVICE_NAME,
        "version": settings.VERSION,
        "database": {
            "status": "connected" if db_healthy else "disconnected",
            "error": db_error,
        },
        "features": {
            "embeddings": bool(settings.ARTEMIS_API_KEY),
            "retention_days": settings.LOG_RETENTION_DAYS,
        }
    }


@app.get("/metrics")
async def get_metrics():
    """
    Prometheus-compatible metrics endpoint.

    Returns key operational metrics for monitoring.
    """
    # Get metrics from middleware
    global metrics_middleware
    if metrics_middleware:
        return metrics_middleware.get_metrics()

    return {
        "uptime_seconds": 0,
        "total_requests": 0,
        "error_count": 0,
        "error_rate": 0,
        "avg_latency_ms": 0,
        "status_codes": {},
    }


@app.get("/metrics/prometheus", response_class=PlainTextResponse)
async def get_prometheus_metrics():
    """
    Prometheus text format metrics.

    Can be scraped directly by Prometheus.
    """
    global metrics_middleware
    if not metrics_middleware:
        return ""

    m = metrics_middleware.get_metrics()

    lines = [
        f"# HELP logr_uptime_seconds Time since service started",
        f"# TYPE logr_uptime_seconds gauge",
        f'logr_uptime_seconds {m["uptime_seconds"]:.2f}',
        f"# HELP logr_requests_total Total number of requests",
        f"# TYPE logr_requests_total counter",
        f'logr_requests_total {m["total_requests"]}',
        f"# HELP logr_errors_total Total number of errors",
        f"# TYPE logr_errors_total counter",
        f'logr_errors_total {m["error_count"]}',
        f"# HELP logr_request_latency_ms Average request latency in milliseconds",
        f"# TYPE logr_request_latency_ms gauge",
        f'logr_request_latency_ms {m["avg_latency_ms"]:.2f}',
    ]

    for status_code, count in m.get("status_codes", {}).items():
        lines.append(f'logr_status_code_total{{code="{status_code}"}} {count}')

    return "\n".join(lines)


@app.get("/")
async def root():
    """API info."""
    return {
        "service": "logr",
        "version": settings.VERSION,
        "description": "Centralized structured logging for AI-powered analysis",
        "docs": "/docs",
        "endpoints": {
            "logs": "/v1/logs",
            "spans": "/v1/spans",
            "search": "/v1/search",
            "admin": "/v1/admin",
            "health": "/health",
            "metrics": "/metrics",
        }
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )
