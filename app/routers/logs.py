"""Log ingestion and query endpoints - OpenTelemetry compatible."""
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_, or_, func, text
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import LogEntry, LogEvent, APIKey
from app.auth import verify_write_permission, verify_read_permission
from app.middleware import (
    validate_log_level,
    validate_event_type,
    validate_message_length,
    validate_context_size,
    VALID_LOG_LEVELS,
    VALID_EVENT_TYPES,
)

router = APIRouter(prefix="/v1/logs", tags=["Logs"])


# ============================================================================
# Request/Response Models
# ============================================================================

class LogEventCreate(BaseModel):
    """Event payload (prompt, completion, tool_call, etc.)"""
    event_type: str = Field(..., description="Type: prompt/completion/tool_call/tool_result/retrieval/context/system_prompt")
    content: Optional[str] = Field(None, description="The payload content")
    content_type: str = Field("text/plain", description="MIME type")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    sequence: int = Field(0, description="Order within the log entry")
    duration_ms: Optional[float] = None


class LogEntryCreate(BaseModel):
    """Single log entry with optional events."""
    # Required
    service: str = Field(..., description="Service name (e.g., 'taskr-bot')")
    level: str = Field(..., description="Log level: debug/info/warn/error/fatal")
    message: str = Field(..., description="Log message")

    # Optional context
    context: Dict[str, Any] = Field(default_factory=dict, description="Structured context data")
    environment: str = Field("production", description="Environment: production/staging/dev")
    host: Optional[str] = Field(None, description="Hostname or container ID")
    version: Optional[str] = Field(None, description="Service version")

    # Trace correlation (OpenTelemetry compatible)
    trace_id: Optional[str] = Field(None, description="W3C trace ID for cross-service correlation")
    span_id: Optional[str] = Field(None, description="This operation's span ID")
    parent_span_id: Optional[str] = Field(None, description="Parent span for hierarchy")

    # Request context
    request_id: Optional[str] = Field(None, description="Single request tracking ID")
    user_id: Optional[str] = Field(None, description="User attribution")
    session_id: Optional[str] = Field(None, description="Session tracking")

    # Timing
    timestamp: Optional[datetime] = Field(None, description="Event timestamp (defaults to now)")
    duration_ms: Optional[float] = Field(None, description="Operation duration in milliseconds")

    # LLM-specific (optional)
    model: Optional[str] = Field(None, description="LLM model name (e.g., 'claude-3-opus')")
    tokens_in: Optional[int] = Field(None, description="Input tokens")
    tokens_out: Optional[int] = Field(None, description="Output tokens")
    cost_usd: Optional[float] = Field(None, description="Computed cost in USD")

    # Error details (optional)
    error_type: Optional[str] = Field(None, description="Exception class name")
    error_message: Optional[str] = Field(None, description="Error description")
    stack_trace: Optional[str] = Field(None, description="Full stack trace")

    # Large payload events (prompts, completions, etc.)
    events: List[LogEventCreate] = Field(default_factory=list, description="Associated events (prompts, completions)")


class LogEventResponse(BaseModel):
    """Event response."""
    id: UUID
    event_type: str
    content: Optional[str]
    content_type: str
    event_metadata: Dict[str, Any] = Field(default_factory=dict)
    sequence: int
    duration_ms: Optional[float]
    timestamp: datetime

    class Config:
        from_attributes = True


class LogEntryResponse(BaseModel):
    """Log entry response."""
    id: UUID
    service: str
    level: str
    message: str
    context: Dict[str, Any]
    environment: str
    host: Optional[str]
    version: Optional[str]

    trace_id: Optional[str]
    span_id: Optional[str]
    parent_span_id: Optional[str]

    request_id: Optional[str]
    user_id: Optional[str]
    session_id: Optional[str]

    timestamp: datetime
    duration_ms: Optional[float]
    created_at: datetime

    model: Optional[str]
    tokens_in: Optional[int]
    tokens_out: Optional[int]
    cost_usd: Optional[float]

    error_type: Optional[str]
    error_message: Optional[str]

    events: List[LogEventResponse] = []

    class Config:
        from_attributes = True


class LogEntrySummary(BaseModel):
    """Compact log entry for list views."""
    id: UUID
    service: str
    level: str
    message: str
    timestamp: datetime
    trace_id: Optional[str]
    duration_ms: Optional[float]
    error_type: Optional[str]
    model: Optional[str]
    event_count: int = 0

    class Config:
        from_attributes = True


class BatchLogRequest(BaseModel):
    """Batch log submission."""
    logs: List[LogEntryCreate] = Field(..., max_length=1000)


class BatchLogResponse(BaseModel):
    """Batch log response."""
    accepted: int
    failed: int
    errors: List[str] = []


class LogSearchResponse(BaseModel):
    """Search results."""
    logs: List[LogEntrySummary]
    total: int
    page: int
    page_size: int
    has_more: bool


class TraceResponse(BaseModel):
    """Full trace with all related logs."""
    trace_id: str
    logs: List[LogEntryResponse]
    span_count: int
    services: List[str]
    start_time: datetime
    end_time: Optional[datetime]
    total_duration_ms: Optional[float]


# ============================================================================
# Endpoints
# ============================================================================

@router.post("", response_model=LogEntryResponse, status_code=201)
async def create_log(
    log: LogEntryCreate,
    db: AsyncSession = Depends(get_db),
    api_key: APIKey = Depends(verify_write_permission),
):
    """
    Submit a single log entry with optional events.

    Example - Simple log:
    ```json
    {
        "service": "taskr-bot",
        "level": "info",
        "message": "User request processed",
        "duration_ms": 145.5
    }
    ```

    Example - LLM operation with events:
    ```json
    {
        "service": "taskr-bot",
        "level": "info",
        "message": "LLM completion successful",
        "trace_id": "abc123",
        "model": "claude-3-opus",
        "tokens_in": 500,
        "tokens_out": 1200,
        "cost_usd": 0.045,
        "duration_ms": 3500,
        "events": [
            {"event_type": "system_prompt", "content": "You are a helpful assistant..."},
            {"event_type": "prompt", "content": "What is the weather?", "sequence": 1},
            {"event_type": "completion", "content": "I don't have access to...", "sequence": 2}
        ]
    }
    ```
    """
    # Validate inputs
    try:
        validated_level = validate_log_level(log.level)
        validate_message_length(log.message)
        if log.context:
            validate_context_size(log.context)
        for event in log.events:
            validate_event_type(event.event_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    entry = LogEntry(
        service=log.service,
        level=validated_level,
        message=log.message,
        context=log.context,
        environment=log.environment,
        host=log.host,
        version=log.version,
        trace_id=log.trace_id,
        span_id=log.span_id,
        parent_span_id=log.parent_span_id,
        request_id=log.request_id,
        user_id=log.user_id,
        session_id=log.session_id,
        timestamp=log.timestamp or datetime.now(timezone.utc),
        duration_ms=log.duration_ms,
        model=log.model,
        tokens_in=log.tokens_in,
        tokens_out=log.tokens_out,
        cost_usd=log.cost_usd,
        error_type=log.error_type,
        error_message=log.error_message,
        stack_trace=log.stack_trace,
    )

    # Add events
    for event_data in log.events:
        event = LogEvent(
            event_type=event_data.event_type,
            content=event_data.content,
            content_type=event_data.content_type,
            event_metadata=event_data.metadata,
            sequence=event_data.sequence,
            duration_ms=event_data.duration_ms,
        )
        entry.events.append(event)

    db.add(entry)
    await db.commit()
    await db.refresh(entry, ["events"])

    return entry


@router.post("/batch", response_model=BatchLogResponse, status_code=201)
async def create_logs_batch(
    batch: BatchLogRequest,
    db: AsyncSession = Depends(get_db),
    api_key: APIKey = Depends(verify_write_permission),
):
    """
    Submit multiple log entries in a single request.
    Accepts up to 1000 logs per batch for efficient bulk ingestion.
    """
    accepted = 0
    failed = 0
    errors = []

    for i, log in enumerate(batch.logs):
        try:
            entry = LogEntry(
                service=log.service,
                level=log.level.lower(),
                message=log.message,
                context=log.context,
                environment=log.environment,
                host=log.host,
                version=log.version,
                trace_id=log.trace_id,
                span_id=log.span_id,
                parent_span_id=log.parent_span_id,
                request_id=log.request_id,
                user_id=log.user_id,
                session_id=log.session_id,
                timestamp=log.timestamp or datetime.now(timezone.utc),
                duration_ms=log.duration_ms,
                model=log.model,
                tokens_in=log.tokens_in,
                tokens_out=log.tokens_out,
                cost_usd=log.cost_usd,
                error_type=log.error_type,
                error_message=log.error_message,
                stack_trace=log.stack_trace,
            )

            for event_data in log.events:
                event = LogEvent(
                    event_type=event_data.event_type,
                    content=event_data.content,
                    content_type=event_data.content_type,
                    event_metadata=event_data.metadata,
                    sequence=event_data.sequence,
                    duration_ms=event_data.duration_ms,
                )
                entry.events.append(event)

            db.add(entry)
            accepted += 1
        except Exception as e:
            failed += 1
            errors.append(f"Log {i}: {str(e)}")

    if accepted > 0:
        await db.commit()

    return BatchLogResponse(accepted=accepted, failed=failed, errors=errors[:10])


@router.get("", response_model=LogSearchResponse)
async def list_logs(
    service: Optional[str] = Query(None, description="Filter by service name"),
    level: Optional[str] = Query(None, description="Filter by log level"),
    environment: Optional[str] = Query(None, description="Filter by environment"),
    trace_id: Optional[str] = Query(None, description="Filter by trace ID"),
    span_id: Optional[str] = Query(None, description="Filter by span ID"),
    request_id: Optional[str] = Query(None, description="Filter by request ID"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    session_id: Optional[str] = Query(None, description="Filter by session ID"),
    model: Optional[str] = Query(None, description="Filter by LLM model"),
    error_type: Optional[str] = Query(None, description="Filter by error type"),
    has_error: Optional[bool] = Query(None, description="Filter to only errors"),
    since: Optional[datetime] = Query(None, description="Logs after this timestamp"),
    until: Optional[datetime] = Query(None, description="Logs before this timestamp"),
    min_duration_ms: Optional[float] = Query(None, description="Minimum duration"),
    max_duration_ms: Optional[float] = Query(None, description="Maximum duration"),
    search: Optional[str] = Query(None, description="Full-text search in message"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=500, description="Results per page"),
    db: AsyncSession = Depends(get_db),
    api_key: APIKey = Depends(verify_read_permission),
):
    """
    Query logs with comprehensive filters.

    Examples:
    - `/v1/logs?service=taskr-bot&level=error` - All errors from taskr-bot
    - `/v1/logs?trace_id=abc123` - All logs for a specific trace
    - `/v1/logs?model=claude-3-opus&min_duration_ms=5000` - Slow Claude calls
    - `/v1/logs?has_error=true&since=2026-01-31T00:00:00Z` - Recent errors
    """
    query = select(LogEntry)
    count_query = select(func.count(LogEntry.id))

    conditions = []

    if service:
        conditions.append(LogEntry.service == service)
    if level:
        conditions.append(LogEntry.level == level.lower())
    if environment:
        conditions.append(LogEntry.environment == environment)
    if trace_id:
        conditions.append(LogEntry.trace_id == trace_id)
    if span_id:
        conditions.append(LogEntry.span_id == span_id)
    if request_id:
        conditions.append(LogEntry.request_id == request_id)
    if user_id:
        conditions.append(LogEntry.user_id == user_id)
    if session_id:
        conditions.append(LogEntry.session_id == session_id)
    if model:
        conditions.append(LogEntry.model == model)
    if error_type:
        conditions.append(LogEntry.error_type == error_type)
    if has_error is True:
        conditions.append(LogEntry.error_type.isnot(None))
    if since:
        conditions.append(LogEntry.timestamp >= since)
    if until:
        conditions.append(LogEntry.timestamp <= until)
    if min_duration_ms is not None:
        conditions.append(LogEntry.duration_ms >= min_duration_ms)
    if max_duration_ms is not None:
        conditions.append(LogEntry.duration_ms <= max_duration_ms)
    if search:
        conditions.append(LogEntry.message.ilike(f"%{search}%"))

    if conditions:
        query = query.where(and_(*conditions))
        count_query = count_query.where(and_(*conditions))

    # Get total count
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination and ordering
    offset = (page - 1) * page_size
    query = (
        query
        .options(selectinload(LogEntry.events))
        .order_by(desc(LogEntry.timestamp))
        .offset(offset)
        .limit(page_size)
    )

    result = await db.execute(query)
    logs = result.scalars().all()

    return LogSearchResponse(
        logs=[
            LogEntrySummary(
                id=log.id,
                service=log.service,
                level=log.level,
                message=log.message,
                timestamp=log.timestamp,
                trace_id=log.trace_id,
                duration_ms=log.duration_ms,
                error_type=log.error_type,
                model=log.model,
                event_count=len(log.events),
            )
            for log in logs
        ],
        total=total,
        page=page,
        page_size=page_size,
        has_more=(offset + len(logs)) < total,
    )


@router.get("/trace/{trace_id}", response_model=TraceResponse)
async def get_trace(
    trace_id: str,
    db: AsyncSession = Depends(get_db),
    api_key: APIKey = Depends(verify_read_permission),
):
    """
    Get all logs for a distributed trace.

    Returns logs ordered by timestamp with full event details,
    useful for debugging cross-service requests.
    """
    result = await db.execute(
        select(LogEntry)
        .where(LogEntry.trace_id == trace_id)
        .options(selectinload(LogEntry.events))
        .order_by(LogEntry.timestamp)
    )
    logs = result.scalars().all()

    if not logs:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")

    services = list(set(log.service for log in logs))
    start_time = min(log.timestamp for log in logs)
    end_time = max(log.timestamp for log in logs)
    total_duration = sum(log.duration_ms or 0 for log in logs)

    return TraceResponse(
        trace_id=trace_id,
        logs=[LogEntryResponse.model_validate(log) for log in logs],
        span_count=len(set(log.span_id for log in logs if log.span_id)),
        services=services,
        start_time=start_time,
        end_time=end_time,
        total_duration_ms=total_duration if total_duration > 0 else None,
    )


@router.get("/services", response_model=List[str])
async def list_services(
    db: AsyncSession = Depends(get_db),
    api_key: APIKey = Depends(verify_read_permission),
):
    """List all services that have submitted logs."""
    result = await db.execute(
        select(LogEntry.service).distinct().order_by(LogEntry.service)
    )
    return [row[0] for row in result.all()]


@router.get("/models", response_model=List[str])
async def list_models(
    db: AsyncSession = Depends(get_db),
    api_key: APIKey = Depends(verify_read_permission),
):
    """List all LLM models that appear in logs."""
    result = await db.execute(
        select(LogEntry.model)
        .where(LogEntry.model.isnot(None))
        .distinct()
        .order_by(LogEntry.model)
    )
    return [row[0] for row in result.all()]


@router.get("/stats")
async def get_stats(
    service: Optional[str] = Query(None, description="Filter by service"),
    hours: int = Query(24, ge=1, le=168, description="Time window in hours"),
    db: AsyncSession = Depends(get_db),
    api_key: APIKey = Depends(verify_read_permission),
):
    """
    Get comprehensive log statistics for the specified time window.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    conditions = [LogEntry.timestamp >= since]
    if service:
        conditions.append(LogEntry.service == service)

    # Count by level
    level_query = (
        select(LogEntry.level, func.count(LogEntry.id))
        .where(and_(*conditions))
        .group_by(LogEntry.level)
    )
    level_result = await db.execute(level_query)
    by_level = {row[0]: row[1] for row in level_result.all()}

    # Count by service
    service_query = (
        select(LogEntry.service, func.count(LogEntry.id))
        .where(and_(*conditions))
        .group_by(LogEntry.service)
        .order_by(desc(func.count(LogEntry.id)))
        .limit(20)
    )
    service_result = await db.execute(service_query)
    by_service = {row[0]: row[1] for row in service_result.all()}

    # Count by model (LLM stats)
    model_query = (
        select(LogEntry.model, func.count(LogEntry.id), func.sum(LogEntry.tokens_in), func.sum(LogEntry.tokens_out), func.sum(LogEntry.cost_usd))
        .where(and_(*conditions, LogEntry.model.isnot(None)))
        .group_by(LogEntry.model)
        .order_by(desc(func.count(LogEntry.id)))
    )
    model_result = await db.execute(model_query)
    by_model = {
        row[0]: {
            "count": row[1],
            "tokens_in": row[2] or 0,
            "tokens_out": row[3] or 0,
            "cost_usd": float(row[4] or 0),
        }
        for row in model_result.all()
    }

    # Error stats
    error_query = (
        select(LogEntry.error_type, func.count(LogEntry.id))
        .where(and_(*conditions, LogEntry.error_type.isnot(None)))
        .group_by(LogEntry.error_type)
        .order_by(desc(func.count(LogEntry.id)))
        .limit(10)
    )
    error_result = await db.execute(error_query)
    by_error = {row[0]: row[1] for row in error_result.all()}

    # Latency stats
    latency_query = (
        select(
            func.avg(LogEntry.duration_ms),
            func.min(LogEntry.duration_ms),
            func.max(LogEntry.duration_ms),
            func.percentile_cont(0.5).within_group(LogEntry.duration_ms),
            func.percentile_cont(0.95).within_group(LogEntry.duration_ms),
            func.percentile_cont(0.99).within_group(LogEntry.duration_ms),
        )
        .where(and_(*conditions, LogEntry.duration_ms.isnot(None)))
    )
    try:
        latency_result = await db.execute(latency_query)
        latency_row = latency_result.first()
        latency = {
            "avg_ms": float(latency_row[0]) if latency_row[0] else None,
            "min_ms": float(latency_row[1]) if latency_row[1] else None,
            "max_ms": float(latency_row[2]) if latency_row[2] else None,
            "p50_ms": float(latency_row[3]) if latency_row[3] else None,
            "p95_ms": float(latency_row[4]) if latency_row[4] else None,
            "p99_ms": float(latency_row[5]) if latency_row[5] else None,
        }
    except Exception:
        latency = {}

    # Total
    total_query = select(func.count(LogEntry.id)).where(and_(*conditions))
    total_result = await db.execute(total_query)
    total = total_result.scalar()

    return {
        "time_window_hours": hours,
        "total": total,
        "by_level": by_level,
        "by_service": by_service,
        "by_model": by_model,
        "by_error": by_error,
        "latency": latency,
    }


@router.get("/{log_id}", response_model=LogEntryResponse)
async def get_log(
    log_id: UUID,
    db: AsyncSession = Depends(get_db),
    api_key: APIKey = Depends(verify_read_permission),
):
    """Get a specific log entry by ID with all events."""
    result = await db.execute(
        select(LogEntry)
        .where(LogEntry.id == log_id)
        .options(selectinload(LogEntry.events))
    )
    log = result.scalar_one_or_none()

    if not log:
        raise HTTPException(status_code=404, detail="Log not found")

    return log
