"""Log ingestion and query endpoints."""
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_, or_, func, text

from app.database import get_db
from app.models import LogEntry, APIKey
from app.auth import verify_write_permission, verify_read_permission

router = APIRouter(prefix="/v1/logs", tags=["Logs"])


# Request/Response Models

class LogEntryCreate(BaseModel):
    """Single log entry."""
    service: str = Field(..., description="Service name (e.g., 'taskr-bot')")
    level: str = Field(..., description="Log level: debug/info/warn/error/fatal")
    message: str = Field(..., description="Log message")
    context: Dict[str, Any] = Field(default_factory=dict, description="Structured context data")
    trace_id: Optional[str] = Field(None, description="Cross-service correlation ID")
    request_id: Optional[str] = Field(None, description="Single request tracking ID")
    user_id: Optional[str] = Field(None, description="User attribution")
    timestamp: Optional[datetime] = Field(None, description="Event timestamp (defaults to now)")
    environment: str = Field("production", description="Environment: production/staging/dev")


class LogEntryResponse(BaseModel):
    """Log entry response."""
    id: UUID
    service: str
    level: str
    message: str
    context: Dict[str, Any]
    trace_id: Optional[str]
    request_id: Optional[str]
    user_id: Optional[str]
    timestamp: datetime
    environment: str
    created_at: datetime

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
    logs: List[LogEntryResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


# Endpoints

@router.post("", response_model=LogEntryResponse, status_code=201)
async def create_log(
    log: LogEntryCreate,
    db: AsyncSession = Depends(get_db),
    api_key: APIKey = Depends(verify_write_permission),
):
    """
    Submit a single log entry.

    Example:
    ```json
    {
        "service": "taskr-bot",
        "level": "error",
        "message": "Artemis timeout after 30s",
        "context": {"latency_ms": 30000, "model": "claude-3-opus"},
        "trace_id": "trace_abc123"
    }
    ```
    """
    entry = LogEntry(
        service=log.service,
        level=log.level.lower(),
        message=log.message,
        context=log.context,
        trace_id=log.trace_id,
        request_id=log.request_id,
        user_id=log.user_id,
        timestamp=log.timestamp or datetime.now(timezone.utc),
        environment=log.environment,
    )

    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    return entry


@router.post("/batch", response_model=BatchLogResponse, status_code=201)
async def create_logs_batch(
    batch: BatchLogRequest,
    db: AsyncSession = Depends(get_db),
    api_key: APIKey = Depends(verify_write_permission),
):
    """
    Submit multiple log entries in a single request.
    Accepts up to 1000 logs per batch.
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
                trace_id=log.trace_id,
                request_id=log.request_id,
                user_id=log.user_id,
                timestamp=log.timestamp or datetime.now(timezone.utc),
                environment=log.environment,
            )
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
    request_id: Optional[str] = Query(None, description="Filter by request ID"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    since: Optional[datetime] = Query(None, description="Logs after this timestamp"),
    until: Optional[datetime] = Query(None, description="Logs before this timestamp"),
    search: Optional[str] = Query(None, description="Full-text search in message"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=500, description="Results per page"),
    db: AsyncSession = Depends(get_db),
    api_key: APIKey = Depends(verify_read_permission),
):
    """
    Query logs with filters.

    Examples:
    - `/v1/logs?service=taskr-bot&level=error` - All errors from taskr-bot
    - `/v1/logs?trace_id=trace_abc123` - All logs for a specific trace
    - `/v1/logs?since=2026-01-31T00:00:00Z&search=timeout` - Recent timeout logs
    """
    # Build query
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
    if request_id:
        conditions.append(LogEntry.request_id == request_id)
    if user_id:
        conditions.append(LogEntry.user_id == user_id)
    if since:
        conditions.append(LogEntry.timestamp >= since)
    if until:
        conditions.append(LogEntry.timestamp <= until)
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
    query = query.order_by(desc(LogEntry.timestamp)).offset(offset).limit(page_size)

    result = await db.execute(query)
    logs = result.scalars().all()

    return LogSearchResponse(
        logs=[LogEntryResponse.model_validate(log) for log in logs],
        total=total,
        page=page,
        page_size=page_size,
        has_more=(offset + len(logs)) < total,
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


@router.get("/stats")
async def get_stats(
    service: Optional[str] = Query(None, description="Filter by service"),
    hours: int = Query(24, ge=1, le=168, description="Time window in hours"),
    db: AsyncSession = Depends(get_db),
    api_key: APIKey = Depends(verify_read_permission),
):
    """
    Get log statistics for the specified time window.

    Returns counts by level and service.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Base condition
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

    # Total
    total_query = select(func.count(LogEntry.id)).where(and_(*conditions))
    total_result = await db.execute(total_query)
    total = total_result.scalar()

    return {
        "time_window_hours": hours,
        "total": total,
        "by_level": by_level,
        "by_service": by_service,
    }


@router.get("/{log_id}", response_model=LogEntryResponse)
async def get_log(
    log_id: UUID,
    db: AsyncSession = Depends(get_db),
    api_key: APIKey = Depends(verify_read_permission),
):
    """Get a specific log entry by ID."""
    result = await db.execute(
        select(LogEntry).where(LogEntry.id == log_id)
    )
    log = result.scalar_one_or_none()

    if not log:
        raise HTTPException(status_code=404, detail="Log not found")

    return log
