"""Logr - Centralized structured logging service for AI-powered analysis."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import init_db
from app.routers import logs, spans, search, admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    await init_db()
    yield


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

# LLM operation with events
httpx.post(
    "https://logr.jettaintelligence.com/v1/logs",
    headers={"Authorization": "Bearer logr_xxx"},
    json={
        "service": "chatbot",
        "level": "info",
        "message": "LLM completion",
        "model": "claude-3-opus",
        "tokens_in": 500,
        "tokens_out": 1200,
        "cost_usd": 0.045,
        "duration_ms": 3500,
        "events": [
            {"event_type": "prompt", "content": "What is..."},
            {"event_type": "completion", "content": "The answer is..."}
        ]
    }
)
```
    """,
    version=settings.VERSION,
    lifespan=lifespan,
)

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
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": settings.SERVICE_NAME,
        "version": settings.VERSION,
        "features": {
            "embeddings": bool(settings.ARTEMIS_API_KEY),
            "retention_days": settings.LOG_RETENTION_DAYS,
        }
    }


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
        }
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )
