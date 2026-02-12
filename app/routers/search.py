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
    mode: Optional[str] = Field(
        "ensemble",
        description="Search mode: ensemble (default), vector, bm25, text",
    )


class SearchResult(BaseModel):
    """Search result with fused score and signal breakdown."""
    id: UUID
    service: str
    level: str
    message: str
    timestamp: datetime
    similarity: float
    trace_id: Optional[str] = None
    error_type: Optional[str] = None
    signals: Optional[Dict[str, float]] = None

    class Config:
        from_attributes = True


class SemanticSearchResponse(BaseModel):
    """Semantic search response."""
    query: str
    results: List[SearchResult]
    total: int
    signals_used: Optional[Dict[str, bool]] = None
    search_mode: Optional[str] = None


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

async def get_embedding(query_text: str) -> Optional[List[float]]:
    """Get embedding for text using Artemis."""
    if not settings.ARTEMIS_API_KEY:
        return None

    import httpx

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.ARTEMIS_URL}/v1/embeddings",
                headers={"Authorization": f"Bearer {settings.ARTEMIS_API_KEY}"},
                json={"input": query_text, "model": settings.EMBEDDING_MODEL},
            )
            response.raise_for_status()
            return response.json()["data"][0]["embedding"]
    except Exception:
        return None


# ============================================================================
# Text Fallback
# ============================================================================

async def _text_fallback_search(
    db: AsyncSession, request: SemanticSearchRequest
) -> SemanticSearchResponse:
    """ILIKE text fallback when no other signals are available."""
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
                similarity=1.0,
                trace_id=log.trace_id,
                error_type=log.error_type,
            )
            for log in logs
        ],
        total=len(logs),
        signals_used={"text_fallback": True},
        search_mode="text",
    )


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
    Ensemble search over log messages using BM25 + vector + heuristics with RRF fusion.

    Combines:
    - BM25 full-text search (keyword matching via PostgreSQL tsvector)
    - Vector similarity (semantic meaning via pgvector embeddings)
    - Heuristics (recency boost, error level weighting)

    Results are fused using Reciprocal Rank Fusion (RRF).
    Degrades gracefully when embeddings are unavailable.
    """
    from app.search_engine import ensemble_search

    mode = (request.mode or "ensemble").lower()

    # Legacy text fallback mode
    if mode == "text":
        return await _text_fallback_search(db, request)

    # Get query embedding (may return None if Artemis is down)
    query_embedding = None
    if mode in ("ensemble", "vector"):
        query_embedding = await get_embedding(request.query)

    # Vector-only mode without embedding available: degrade to ensemble
    if mode == "vector" and not query_embedding:
        mode = "ensemble"

    # Run ensemble search
    fused_results, signals_used = await ensemble_search(
        db,
        request.query,
        query_embedding,
        service=request.service,
        level=request.level,
        since=request.since,
        limit=request.limit,
    )

    # If ensemble returned nothing, fall back to text
    if not fused_results:
        return await _text_fallback_search(db, request)

    return SemanticSearchResponse(
        query=request.query,
        results=[
            SearchResult(
                id=r["id"],
                service=r["service"],
                level=r["level"],
                message=r["message"],
                timestamp=r["timestamp"],
                similarity=r.get("similarity", 0.0),
                trace_id=r.get("trace_id"),
                error_type=r.get("error_type"),
                signals=r.get("signals"),
            )
            for r in fused_results
        ],
        total=len(fused_results),
        signals_used=signals_used,
        search_mode=mode,
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
    embedding_str = "[" + ",".join(str(x) for x in ref_log.embedding) + "]"

    conditions = ["embedding IS NOT NULL", "id != :ref_id"]
    params = {"embedding": embedding_str, "ref_id": request.log_id, "limit": request.limit}

    if request.exclude_same_trace and ref_log.trace_id:
        conditions.append("(trace_id IS NULL OR trace_id != :trace_id)")
        params["trace_id"] = ref_log.trace_id

    where_clause = " AND ".join(conditions)

    query = text(f"""
        SELECT id, service, level, message, timestamp, trace_id, error_type,
               1 - (embedding <=> CAST(:embedding AS vector)) as similarity
        FROM log_entries
        WHERE {where_clause}
        ORDER BY embedding <=> CAST(:embedding AS vector)
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
    message_prefix = func.left(LogEntry.message, 100)
    query = (
        select(
            LogEntry.error_type,
            message_prefix.label("message_prefix"),
            func.count(LogEntry.id).label("count"),
            func.min(LogEntry.timestamp).label("first_seen"),
            func.max(LogEntry.timestamp).label("last_seen"),
            func.array_agg(func.distinct(LogEntry.service)).label("services"),
        )
        .where(and_(*conditions))
        .group_by(LogEntry.error_type, message_prefix)
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
