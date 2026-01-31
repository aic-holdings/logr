"""Middleware for rate limiting, request validation, and metrics."""
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, Tuple

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple in-memory rate limiting per API key.

    For production at scale, use Redis-based rate limiting.
    """

    def __init__(self, app, requests_per_minute: int = 1000):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.request_counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/", "/docs", "/openapi.json"]:
            return await call_next(request)

        # Extract API key from header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            key = auth_header[7:20]  # Use prefix as identifier
        else:
            key = request.client.host if request.client else "unknown"

        # Check rate limit
        count, window_start = self.request_counts[key]
        now = time.time()

        # Reset window if expired (1 minute)
        if now - window_start > 60:
            self.request_counts[key] = (1, now)
        else:
            if count >= self.requests_per_minute:
                return Response(
                    content='{"detail": "Rate limit exceeded. Try again later."}',
                    status_code=429,
                    media_type="application/json",
                    headers={"Retry-After": str(int(60 - (now - window_start)))}
                )
            self.request_counts[key] = (count + 1, window_start)

        return await call_next(request)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Limit request body size to prevent abuse."""

    def __init__(self, app, max_size_mb: int = 10):
        super().__init__(app)
        self.max_size_bytes = max_size_mb * 1024 * 1024

    async def dispatch(self, request: Request, call_next) -> Response:
        content_length = request.headers.get("content-length")

        if content_length and int(content_length) > self.max_size_bytes:
            return Response(
                content=f'{{"detail": "Request body too large. Maximum size: {self.max_size_bytes // (1024*1024)}MB"}}',
                status_code=413,
                media_type="application/json"
            )

        return await call_next(request)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Collect basic metrics for monitoring."""

    def __init__(self, app):
        super().__init__(app)
        self.request_count = 0
        self.error_count = 0
        self.latency_sum = 0.0
        self.latency_count = 0
        self.status_codes: Dict[int, int] = defaultdict(int)
        self.start_time = time.time()

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.time()

        response = await call_next(request)

        duration = time.time() - start
        self.request_count += 1
        self.latency_sum += duration
        self.latency_count += 1
        self.status_codes[response.status_code] += 1

        if response.status_code >= 400:
            self.error_count += 1

        return response

    def get_metrics(self) -> dict:
        """Get current metrics."""
        uptime = time.time() - self.start_time
        avg_latency = self.latency_sum / self.latency_count if self.latency_count > 0 else 0

        return {
            "uptime_seconds": uptime,
            "total_requests": self.request_count,
            "error_count": self.error_count,
            "error_rate": self.error_count / self.request_count if self.request_count > 0 else 0,
            "avg_latency_ms": avg_latency * 1000,
            "status_codes": dict(self.status_codes),
        }


# Validation helpers

VALID_LOG_LEVELS = {"debug", "info", "warn", "warning", "error", "fatal", "critical"}
VALID_EVENT_TYPES = {"prompt", "completion", "tool_call", "tool_result", "retrieval", "context", "system_prompt"}

MAX_MESSAGE_LENGTH = 100_000  # 100KB
MAX_CONTEXT_SIZE = 1_000_000  # 1MB
MAX_CONTENT_LENGTH = 10_000_000  # 10MB for events


def validate_log_level(level: str) -> str:
    """Validate and normalize log level."""
    normalized = level.lower()
    if normalized == "warning":
        normalized = "warn"
    if normalized == "critical":
        normalized = "fatal"
    if normalized not in VALID_LOG_LEVELS:
        raise ValueError(f"Invalid log level: {level}. Must be one of: {', '.join(sorted(VALID_LOG_LEVELS))}")
    return normalized


def validate_event_type(event_type: str) -> str:
    """Validate event type."""
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"Invalid event type: {event_type}. Must be one of: {', '.join(sorted(VALID_EVENT_TYPES))}")
    return event_type


def validate_message_length(message: str) -> str:
    """Validate message length."""
    if len(message) > MAX_MESSAGE_LENGTH:
        raise ValueError(f"Message too long. Maximum length: {MAX_MESSAGE_LENGTH} characters")
    return message


def validate_context_size(context: dict) -> dict:
    """Validate context size."""
    import json
    size = len(json.dumps(context))
    if size > MAX_CONTEXT_SIZE:
        raise ValueError(f"Context too large. Maximum size: {MAX_CONTEXT_SIZE} bytes")
    return context
