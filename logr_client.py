"""
Logr Python Client - Simple structured logging to Logr service.

Usage:
    from logr_client import Logr

    logr = Logr(api_key="logr_xxx", service="my-service")

    # Simple logging
    logr.info("User logged in", user_id="U123")
    logr.error("Database timeout", error_type="TimeoutError", duration_ms=30000)

    # LLM operation
    logr.llm(
        message="Completion successful",
        model="claude-3-opus",
        tokens_in=500,
        tokens_out=1200,
        cost_usd=0.045,
        duration_ms=3500,
        prompt="What is the weather?",
        completion="I don't have access to real-time weather data...",
    )

    # With trace context
    with logr.trace("process_request") as trace:
        logr.info("Starting request", trace_id=trace.trace_id)
        # ... do work ...
        logr.info("Request complete", trace_id=trace.trace_id, duration_ms=150)
"""

import uuid
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from contextlib import contextmanager

import httpx


@dataclass
class TraceContext:
    """Context for distributed tracing."""
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    start_time: float = field(default_factory=time.time)

    def child_span(self) -> "TraceContext":
        """Create a child span."""
        return TraceContext(
            trace_id=self.trace_id,
            span_id=f"span_{uuid.uuid4().hex[:16]}",
            parent_span_id=self.span_id,
        )


class Logr:
    """Client for Logr centralized logging service."""

    def __init__(
        self,
        api_key: str,
        service: str,
        url: str = "https://logr.jettaintelligence.com",
        environment: str = "production",
        version: Optional[str] = None,
        timeout: float = 10.0,
        batch_size: int = 100,
        auto_flush: bool = True,
    ):
        self.api_key = api_key
        self.service = service
        self.url = url.rstrip("/")
        self.environment = environment
        self.version = version
        self.timeout = timeout
        self.batch_size = batch_size
        self.auto_flush = auto_flush

        self._buffer: List[Dict] = []
        self._client = httpx.Client(timeout=timeout)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _log(
        self,
        level: str,
        message: str,
        **kwargs,
    ) -> Optional[Dict]:
        """Internal log method."""
        entry = {
            "service": self.service,
            "level": level,
            "message": message,
            "environment": self.environment,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if self.version:
            entry["version"] = self.version

        # Extract known fields from kwargs
        known_fields = [
            "context", "trace_id", "span_id", "parent_span_id",
            "request_id", "user_id", "session_id", "duration_ms",
            "model", "tokens_in", "tokens_out", "cost_usd",
            "error_type", "error_message", "stack_trace",
            "events", "host",
        ]

        context = kwargs.pop("context", {})

        for field_name in known_fields:
            if field_name in kwargs:
                entry[field_name] = kwargs.pop(field_name)

        # Remaining kwargs go to context
        context.update(kwargs)
        if context:
            entry["context"] = context

        if self.auto_flush:
            return self._send(entry)
        else:
            self._buffer.append(entry)
            if len(self._buffer) >= self.batch_size:
                self.flush()
            return None

    def _send(self, entry: Dict) -> Optional[Dict]:
        """Send a single log entry."""
        try:
            response = self._client.post(
                f"{self.url}/v1/logs",
                headers=self._headers(),
                json=entry,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            # Don't fail silently in production - but don't crash either
            print(f"Logr error: {e}")
            return None

    def flush(self) -> Optional[Dict]:
        """Flush buffered logs."""
        if not self._buffer:
            return None

        try:
            response = self._client.post(
                f"{self.url}/v1/logs/batch",
                headers=self._headers(),
                json={"logs": self._buffer},
            )
            response.raise_for_status()
            result = response.json()
            self._buffer.clear()
            return result
        except Exception as e:
            print(f"Logr flush error: {e}")
            return None

    # Convenience methods for log levels
    def debug(self, message: str, **kwargs) -> Optional[Dict]:
        return self._log("debug", message, **kwargs)

    def info(self, message: str, **kwargs) -> Optional[Dict]:
        return self._log("info", message, **kwargs)

    def warn(self, message: str, **kwargs) -> Optional[Dict]:
        return self._log("warn", message, **kwargs)

    def error(self, message: str, **kwargs) -> Optional[Dict]:
        return self._log("error", message, **kwargs)

    def fatal(self, message: str, **kwargs) -> Optional[Dict]:
        return self._log("fatal", message, **kwargs)

    # LLM-specific logging
    def llm(
        self,
        message: str,
        model: str,
        tokens_in: Optional[int] = None,
        tokens_out: Optional[int] = None,
        cost_usd: Optional[float] = None,
        duration_ms: Optional[float] = None,
        prompt: Optional[str] = None,
        completion: Optional[str] = None,
        system_prompt: Optional[str] = None,
        tool_calls: Optional[List[Dict]] = None,
        level: str = "info",
        **kwargs,
    ) -> Optional[Dict]:
        """Log an LLM operation with optional prompt/completion events."""
        events = []

        if system_prompt:
            events.append({
                "event_type": "system_prompt",
                "content": system_prompt,
                "sequence": 0,
            })

        if prompt:
            events.append({
                "event_type": "prompt",
                "content": prompt,
                "sequence": len(events),
            })

        if completion:
            events.append({
                "event_type": "completion",
                "content": completion,
                "sequence": len(events),
            })

        if tool_calls:
            for i, tc in enumerate(tool_calls):
                events.append({
                    "event_type": "tool_call",
                    "content": str(tc),
                    "metadata": tc,
                    "sequence": len(events),
                })

        return self._log(
            level,
            message,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            events=events if events else None,
            **kwargs,
        )

    @contextmanager
    def trace(self, operation: str, parent: Optional[TraceContext] = None):
        """Context manager for distributed tracing."""
        if parent:
            ctx = parent.child_span()
        else:
            ctx = TraceContext(
                trace_id=f"trace_{uuid.uuid4().hex}",
                span_id=f"span_{uuid.uuid4().hex[:16]}",
            )

        self.info(
            f"Starting {operation}",
            trace_id=ctx.trace_id,
            span_id=ctx.span_id,
            parent_span_id=ctx.parent_span_id,
        )

        try:
            yield ctx
        except Exception as e:
            duration = (time.time() - ctx.start_time) * 1000
            self.error(
                f"Error in {operation}: {e}",
                trace_id=ctx.trace_id,
                span_id=ctx.span_id,
                duration_ms=duration,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            raise
        else:
            duration = (time.time() - ctx.start_time) * 1000
            self.info(
                f"Completed {operation}",
                trace_id=ctx.trace_id,
                span_id=ctx.span_id,
                duration_ms=duration,
            )

    def close(self):
        """Flush and close the client."""
        self.flush()
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
