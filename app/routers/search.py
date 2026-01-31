"""Semantic search and AI-powered log analysis."""
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_, func, text

from app.database import get_db
from app.models import LogEntry, APIKey
from app.auth import verify_read_permission
from app.config import settings

router = APIRouter(prefix="/v1/search", tags=["Search"])


# ============================================================================
# Request/Response Models
# ============================================================================

class SemanticSearchRequest(BaseModel):
    """Semantic search request."""
    query: str = Field(..., description="Natural language search query")
    service: Optional[str] = Field(None, description="Filter by service")
    level: Optional[str] = Field(None, description="Filter by log level")
    since: Optional[datetime] = Field(None, description="Search logs after this time")
    limit: int = Field(20, ge=1, le=100, description="Maximum results")


class SearchResult(BaseModel):
    """Search result with similarity score."""
    id: UUID
    service: str
    level: str
    message: str
    timestamp: datetime
    similarity: float
    trace_id: Optional[str]
    error_type: Optional[str]

    class Config:
        from_attributes = True


class SemanticSearchResponse(BaseModel):
    """Semantic search response."""
    query: str
    results: List[SearchResult]
    total: int


class SimilarLogsRequest(BaseModel):
    """Find logs similar to a given log."""
    log_id: UUID = Field(..., description="Reference log ID")
    limit: int = Field(10, ge=1, le=50, description="Maximum results")
    exclude_same_trace: bool = Field(True, description="Exclude logs from same trace")


class PatternAnalysisRequest(BaseModel):
    """Analyze patterns in logs."""
    service: Optional[str] = None
    level: Optional[str] = None
    hours: int = Field(24, ge=1, le=168)
    min_occurrences: int = Field(3, ge=2)


class LogPattern(BaseModel):
    """Detected log pattern."""
    pattern: str
    count: int
    first_seen: datetime
    last_seen: datetime
    services: List[str]
    example_ids: List[UUID]


# ============================================================================
# Embedding Utilities
# ============================================================================

async def get_embedding(text: str) -> Optional[List[float]]:
    """Get embedding for text using Artemis."""
    if not settings.ARTEMIS_API_KEY:
        return None

    import httpx

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.ARTEMIS_URL}/v1/embeddings",
                headers={"Authorization": f"Bearer {settings.ARTEMIS_API_KEY}"},
                json={"input": text, "model": settings.EMBEDDING_MODEL},
            )
            response.raise_for_status()
            return response.json()["data"][0]["embedding"]
    except Exception:
        return None


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/semantic", response_model=SemanticSearchResponse)
async def semantic_search(
    request: SemanticSearchRequest,
    db: AsyncSession = Depends(get_db),
    api_key: APIKey = Depends(verify_read_permission),
):
    """
    Semantic search over log messages using vector similarity.

    Find logs that are semantically similar to a natural language query,
    even if they don't contain the exact keywords.

    Example queries:
    - "database connection timeout"
    - "user authentication failed"
    - "slow API response"
    """
    # Get query embedding
    query_embedding = await get_embedding(request.query)

    if not query_embedding:
        # Fallback to text search if embeddings not available
        conditions = [LogEntry.message.ilike(f"%{request.query}%")]
        if request.service:
            conditions.append(LogEntry.service == request.service)
        if request.level:
            conditions.append(LogEntry.level == request.level.lower())
        if request.since:
            conditions.append(LogEntry.timestamp >= request.since)

        result = await db.execute(
            select(LogEntry)
            .where(and_(*conditions))
            .order_by(desc(LogEntry.timestamp))
            .limit(request.limit)
        )
        logs = result.scalars().all()

        return SemanticSearchResponse(
            query=request.query,
            results=[
                SearchResult(
                    id=log.id,
                    service=log.service,
                    level=log.level,
                    message=log.message,
                    timestamp=log.timestamp,
                    similarity=1.0,  # Text match
                    trace_id=log.trace_id,
                    error_type=log.error_type,
                )
                for log in logs
            ],
            total=len(logs),
        )

    # Vector similarity search
    embedding_str = f"[{','.join(str(x) for x in query_embedding)}]"

    conditions = ["embedding IS NOT NULL"]
    params = {"embedding": embedding_str, "limit": request.limit}

    if request.service:
        conditions.append("service = :service")
        params["service"] = request.service
    if request.level:
        conditions.append("level = :level")
        params["level"] = request.level.lower()
    if request.since:
        conditions.append("timestamp >= :since")
        params["since"] = request.since

    where_clause = " AND ".join(conditions)

    query = text(f"""
        SELECT id, service, level, message, timestamp, trace_id, error_type,
               1 - (embedding <=> :embedding::vector) as similarity
        FROM log_entries
        WHERE {where_clause}
        ORDER BY embedding <=> :embedding::vector
        LIMIT :limit
    """)

    result = await db.execute(query, params)
    rows = result.fetchall()

    return SemanticSearchResponse(
        query=request.query,
        results=[
            SearchResult(
                id=row.id,
                service=row.service,
                level=row.level,
                message=row.message,
                timestamp=row.timestamp,
                similarity=float(row.similarity),
                trace_id=row.trace_id,
                error_type=row.error_type,
            )
            for row in rows
        ],
        total=len(rows),
    )


@router.post("/similar", response_model=List[SearchResult])
async def find_similar_logs(
    request: SimilarLogsRequest,
    db: AsyncSession = Depends(get_db),
    api_key: APIKey = Depends(verify_read_permission),
):
    """
    Find logs similar to a given log entry.

    Useful for:
    - Finding related errors
    - Discovering patterns
    - Root cause analysis
    """
    # Get reference log
    ref_result = await db.execute(
        select(LogEntry).where(LogEntry.id == request.log_id)
    )
    ref_log = ref_result.scalar_one_or_none()

    if not ref_log:
        raise HTTPException(status_code=404, detail="Log not found")

    if not ref_log.embedding:
        # Fallback to text search
        similar_result = await db.execute(
            select(LogEntry)
            .where(
                LogEntry.id != request.log_id,
                LogEntry.message.ilike(f"%{ref_log.message[:50]}%")
            )
            .order_by(desc(LogEntry.timestamp))
            .limit(request.limit)
        )
        similar_logs = similar_result.scalars().all()

        return [
            SearchResult(
                id=log.id,
                service=log.service,
                level=log.level,
                message=log.message,
                timestamp=log.timestamp,
                similarity=0.8,
                trace_id=log.trace_id,
                error_type=log.error_type,
            )
            for log in similar_logs
        ]

    # Vector similarity
    embedding_str = f"[{','.join(str(x) for x in ref_log.embedding)}]"

    conditions = ["embedding IS NOT NULL", "id != :ref_id"]
    params = {"embedding": embedding_str, "ref_id": request.log_id, "limit": request.limit}

    if request.exclude_same_trace and ref_log.trace_id:
        conditions.append("(trace_id IS NULL OR trace_id != :trace_id)")
        params["trace_id"] = ref_log.trace_id

    where_clause = " AND ".join(conditions)

    query = text(f"""
        SELECT id, service, level, message, timestamp, trace_id, error_type,
               1 - (embedding <=> :embedding::vector) as similarity
        FROM log_entries
        WHERE {where_clause}
        ORDER BY embedding <=> :embedding::vector
        LIMIT :limit
    """)

    result = await db.execute(query, params)
    rows = result.fetchall()

    return [
        SearchResult(
            id=row.id,
            service=row.service,
            level=row.level,
            message=row.message,
            timestamp=row.timestamp,
            similarity=float(row.similarity),
            trace_id=row.trace_id,
            error_type=row.error_type,
        )
        for row in rows
    ]


@router.get("/errors/grouped")
async def get_grouped_errors(
    service: Optional[str] = Query(None, description="Filter by service"),
    hours: int = Query(24, ge=1, le=168, description="Time window"),
    min_count: int = Query(2, ge=1, description="Minimum occurrences"),
    db: AsyncSession = Depends(get_db),
    api_key: APIKey = Depends(verify_read_permission),
):
    """
    Get errors grouped by type/message pattern.

    Useful for identifying recurring issues and prioritizing fixes.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    conditions = [
        LogEntry.timestamp >= since,
        LogEntry.level.in_(["error", "fatal"]),
    ]
    if service:
        conditions.append(LogEntry.service == service)

    # Group by error_type and first 100 chars of message
    query = (
        select(
            LogEntry.error_type,
            func.substring(LogEntry.message, 1, 100).label("message_prefix"),
            func.count(LogEntry.id).label("count"),
            func.min(LogEntry.timestamp).label("first_seen"),
            func.max(LogEntry.timestamp).label("last_seen"),
            func.array_agg(func.distinct(LogEntry.service)).label("services"),
        )
        .where(and_(*conditions))
        .group_by(LogEntry.error_type, func.substring(LogEntry.message, 1, 100))
        .having(func.count(LogEntry.id) >= min_count)
        .order_by(desc(func.count(LogEntry.id)))
        .limit(50)
    )

    result = await db.execute(query)
    rows = result.fetchall()

    return {
        "time_window_hours": hours,
        "total_groups": len(rows),
        "groups": [
            {
                "error_type": row.error_type,
                "message_prefix": row.message_prefix,
                "count": row.count,
                "first_seen": row.first_seen,
                "last_seen": row.last_seen,
                "services": list(row.services) if row.services else [],
            }
            for row in rows
        ],
    }


@router.get("/anomalies")
async def detect_anomalies(
    service: Optional[str] = Query(None, description="Filter by service"),
    hours: int = Query(24, ge=1, le=168, description="Time window"),
    db: AsyncSession = Depends(get_db),
    api_key: APIKey = Depends(verify_read_permission),
):
    """
    Detect anomalies in log patterns.

    Identifies:
    - Sudden spikes in error rates
    - Unusual latency patterns
    - New error types
    """
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    comparison_since = since - timedelta(hours=hours)  # Previous period

    conditions = [LogEntry.timestamp >= since]
    prev_conditions = [LogEntry.timestamp >= comparison_since, LogEntry.timestamp < since]

    if service:
        conditions.append(LogEntry.service == service)
        prev_conditions.append(LogEntry.service == service)

    # Current period stats
    current_query = (
        select(
            func.count(LogEntry.id).label("total"),
            func.count(LogEntry.id).filter(LogEntry.level == "error").label("errors"),
            func.avg(LogEntry.duration_ms).label("avg_latency"),
        )
        .where(and_(*conditions))
    )
    current_result = await db.execute(current_query)
    current = current_result.first()

    # Previous period stats
    prev_query = (
        select(
            func.count(LogEntry.id).label("total"),
            func.count(LogEntry.id).filter(LogEntry.level == "error").label("errors"),
            func.avg(LogEntry.duration_ms).label("avg_latency"),
        )
        .where(and_(*prev_conditions))
    )
    prev_result = await db.execute(prev_query)
    prev = prev_result.first()

    # New error types
    new_errors_query = (
        select(LogEntry.error_type)
        .where(and_(*conditions, LogEntry.error_type.isnot(None)))
        .distinct()
        .except_(
            select(LogEntry.error_type)
            .where(and_(*prev_conditions, LogEntry.error_type.isnot(None)))
            .distinct()
        )
    )
    new_errors_result = await db.execute(new_errors_query)
    new_error_types = [row[0] for row in new_errors_result.fetchall()]

    anomalies = []

    # Check error rate spike
    if prev.total and current.total:
        prev_error_rate = (prev.errors or 0) / prev.total
        current_error_rate = (current.errors or 0) / current.total
        if current_error_rate > prev_error_rate * 1.5 and current.errors > 5:
            anomalies.append({
                "type": "error_rate_spike",
                "severity": "high" if current_error_rate > prev_error_rate * 2 else "medium",
                "message": f"Error rate increased from {prev_error_rate:.1%} to {current_error_rate:.1%}",
                "previous": prev_error_rate,
                "current": current_error_rate,
            })

    # Check latency spike
    if prev.avg_latency and current.avg_latency:
        if current.avg_latency > prev.avg_latency * 1.5:
            anomalies.append({
                "type": "latency_spike",
                "severity": "medium",
                "message": f"Average latency increased from {prev.avg_latency:.0f}ms to {current.avg_latency:.0f}ms",
                "previous": float(prev.avg_latency),
                "current": float(current.avg_latency),
            })

    # New error types
    if new_error_types:
        anomalies.append({
            "type": "new_error_types",
            "severity": "medium",
            "message": f"New error types detected: {', '.join(new_error_types[:5])}",
            "error_types": new_error_types,
        })

    return {
        "time_window_hours": hours,
        "anomalies": anomalies,
        "current_period": {
            "total": current.total,
            "errors": current.errors,
            "avg_latency_ms": float(current.avg_latency) if current.avg_latency else None,
        },
        "previous_period": {
            "total": prev.total,
            "errors": prev.errors,
            "avg_latency_ms": float(prev.avg_latency) if prev.avg_latency else None,
        },
    }
