"""Distributed tracing spans - OpenTelemetry compatible."""
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_, func

from app.database import get_db
from app.models import Span, APIKey
from app.auth import verify_write_permission, verify_read_permission

router = APIRouter(prefix="/v1/spans", tags=["Spans"])


# ============================================================================
# Request/Response Models
# ============================================================================

class SpanCreate(BaseModel):
    """Create a span for distributed tracing."""
    trace_id: str = Field(..., description="W3C trace ID")
    span_id: str = Field(..., description="Unique span ID")
    parent_span_id: Optional[str] = Field(None, description="Parent span ID")

    service: str = Field(..., description="Service name")
    operation: str = Field(..., description="Operation name (e.g., 'HTTP GET /api/users')")
    kind: str = Field("internal", description="Span kind: client/server/producer/consumer/internal")

    start_time: datetime = Field(..., description="Span start timestamp")
    end_time: Optional[datetime] = Field(None, description="Span end timestamp")
    duration_ms: Optional[float] = Field(None, description="Duration in milliseconds")

    status: str = Field("ok", description="Status: ok/error/unset")
    status_message: Optional[str] = Field(None, description="Status description")

    attributes: Dict[str, Any] = Field(default_factory=dict, description="Span attributes")
    resource: Dict[str, Any] = Field(default_factory=dict, description="Resource attributes")


class SpanResponse(BaseModel):
    """Span response."""
    id: UUID
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    service: str
    operation: str
    kind: str
    start_time: datetime
    end_time: Optional[datetime]
    duration_ms: Optional[float]
    status: str
    status_message: Optional[str]
    attributes: Dict[str, Any]
    resource: Dict[str, Any]

    class Config:
        from_attributes = True


class SpanTreeNode(BaseModel):
    """Span with children for tree visualization."""
    span: SpanResponse
    children: List["SpanTreeNode"] = []


class TraceSpansResponse(BaseModel):
    """All spans for a trace."""
    trace_id: str
    spans: List[SpanResponse]
    tree: Optional[SpanTreeNode] = None
    services: List[str]
    total_duration_ms: Optional[float]


class BatchSpanRequest(BaseModel):
    """Batch span submission."""
    spans: List[SpanCreate] = Field(..., max_length=1000)


class BatchSpanResponse(BaseModel):
    """Batch span response."""
    accepted: int
    failed: int
    errors: List[str] = []


# ============================================================================
# Endpoints
# ============================================================================

@router.post("", response_model=SpanResponse, status_code=201)
async def create_span(
    span_data: SpanCreate,
    db: AsyncSession = Depends(get_db),
    api_key: APIKey = Depends(verify_write_permission),
):
    """
    Create a span for distributed tracing.

    Example:
    ```json
    {
        "trace_id": "abc123",
        "span_id": "span_001",
        "parent_span_id": null,
        "service": "api-gateway",
        "operation": "HTTP POST /api/chat",
        "kind": "server",
        "start_time": "2026-01-31T20:00:00Z",
        "end_time": "2026-01-31T20:00:03Z",
        "duration_ms": 3000,
        "status": "ok",
        "attributes": {
            "http.method": "POST",
            "http.url": "/api/chat",
            "http.status_code": 200
        }
    }
    ```
    """
    span = Span(
        trace_id=span_data.trace_id,
        span_id=span_data.span_id,
        parent_span_id=span_data.parent_span_id,
        service=span_data.service,
        operation=span_data.operation,
        kind=span_data.kind,
        start_time=span_data.start_time,
        end_time=span_data.end_time,
        duration_ms=span_data.duration_ms,
        status=span_data.status,
        status_message=span_data.status_message,
        attributes=span_data.attributes,
        resource=span_data.resource,
    )

    db.add(span)
    await db.commit()
    await db.refresh(span)

    return span


@router.post("/batch", response_model=BatchSpanResponse, status_code=201)
async def create_spans_batch(
    batch: BatchSpanRequest,
    db: AsyncSession = Depends(get_db),
    api_key: APIKey = Depends(verify_write_permission),
):
    """Submit multiple spans in a single request."""
    accepted = 0
    failed = 0
    errors = []

    for i, span_data in enumerate(batch.spans):
        try:
            span = Span(
                trace_id=span_data.trace_id,
                span_id=span_data.span_id,
                parent_span_id=span_data.parent_span_id,
                service=span_data.service,
                operation=span_data.operation,
                kind=span_data.kind,
                start_time=span_data.start_time,
                end_time=span_data.end_time,
                duration_ms=span_data.duration_ms,
                status=span_data.status,
                status_message=span_data.status_message,
                attributes=span_data.attributes,
                resource=span_data.resource,
            )
            db.add(span)
            accepted += 1
        except Exception as e:
            failed += 1
            errors.append(f"Span {i}: {str(e)}")

    if accepted > 0:
        await db.commit()

    return BatchSpanResponse(accepted=accepted, failed=failed, errors=errors[:10])


@router.get("/trace/{trace_id}", response_model=TraceSpansResponse)
async def get_trace_spans(
    trace_id: str,
    db: AsyncSession = Depends(get_db),
    api_key: APIKey = Depends(verify_read_permission),
):
    """
    Get all spans for a trace with tree structure.

    Returns spans ordered by start time and a hierarchical tree view.
    """
    result = await db.execute(
        select(Span)
        .where(Span.trace_id == trace_id)
        .order_by(Span.start_time)
    )
    spans = result.scalars().all()

    if not spans:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")

    span_responses = [SpanResponse.model_validate(s) for s in spans]

    # Build tree
    span_map = {s.span_id: SpanTreeNode(span=s) for s in span_responses}
    root = None

    for node in span_map.values():
        if node.span.parent_span_id and node.span.parent_span_id in span_map:
            span_map[node.span.parent_span_id].children.append(node)
        elif not node.span.parent_span_id:
            root = node

    services = list(set(s.service for s in spans))
    total_duration = max((s.end_time or s.start_time) for s in spans) - min(s.start_time for s in spans)

    return TraceSpansResponse(
        trace_id=trace_id,
        spans=span_responses,
        tree=root,
        services=services,
        total_duration_ms=total_duration.total_seconds() * 1000 if total_duration else None,
    )


@router.get("", response_model=List[SpanResponse])
async def list_spans(
    trace_id: Optional[str] = Query(None, description="Filter by trace ID"),
    service: Optional[str] = Query(None, description="Filter by service"),
    operation: Optional[str] = Query(None, description="Filter by operation (partial match)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    since: Optional[datetime] = Query(None, description="Spans after this time"),
    until: Optional[datetime] = Query(None, description="Spans before this time"),
    min_duration_ms: Optional[float] = Query(None, description="Minimum duration"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    api_key: APIKey = Depends(verify_read_permission),
):
    """Query spans with filters."""
    query = select(Span)
    conditions = []

    if trace_id:
        conditions.append(Span.trace_id == trace_id)
    if service:
        conditions.append(Span.service == service)
    if operation:
        conditions.append(Span.operation.ilike(f"%{operation}%"))
    if status:
        conditions.append(Span.status == status)
    if since:
        conditions.append(Span.start_time >= since)
    if until:
        conditions.append(Span.start_time <= until)
    if min_duration_ms is not None:
        conditions.append(Span.duration_ms >= min_duration_ms)

    if conditions:
        query = query.where(and_(*conditions))

    offset = (page - 1) * page_size
    query = query.order_by(desc(Span.start_time)).offset(offset).limit(page_size)

    result = await db.execute(query)
    spans = result.scalars().all()

    return [SpanResponse.model_validate(s) for s in spans]
