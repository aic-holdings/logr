"""Admin API for master key operations."""
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func

from app.database import get_db
from app.models import APIKey, ServiceAccount, LogEntry, LogEvent, Span
from app.auth import verify_master_key, generate_api_key, hash_api_key, get_key_prefix
from app.config import settings

router = APIRouter(prefix="/v1/admin", tags=["Admin"])


# Request/Response Models

class CreateServiceAccountRequest(BaseModel):
    name: str
    description: Optional[str] = None


class CreateServiceAccountResponse(BaseModel):
    service_account_id: UUID
    name: str
    api_key: str
    key_prefix: str
    message: str


class ServiceAccountInfo(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    created_at: datetime


class APIKeyInfo(BaseModel):
    id: UUID
    name: str
    key_prefix: str
    can_write: bool
    can_read: bool
    created_at: datetime
    last_used_at: Optional[datetime]
    revoked: bool


class IssueKeyRequest(BaseModel):
    service_account_name: str
    key_name: str = "Default"
    can_write: bool = True
    can_read: bool = True


class IssueKeyResponse(BaseModel):
    id: UUID
    name: str
    api_key: str
    key_prefix: str
    service_account: str


# Endpoints

@router.get("/service-accounts", response_model=dict)
async def list_service_accounts(
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_master_key),
):
    """List all service accounts."""
    result = await db.execute(
        select(ServiceAccount).order_by(ServiceAccount.created_at)
    )
    accounts = result.scalars().all()

    return {
        "service_accounts": [
            ServiceAccountInfo(
                id=a.id,
                name=a.name,
                description=a.description,
                created_at=a.created_at,
            )
            for a in accounts
        ]
    }


@router.post("/service-accounts", response_model=CreateServiceAccountResponse)
async def create_service_account(
    request: CreateServiceAccountRequest,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_master_key),
):
    """Create a new service account with an API key."""
    # Check if name exists
    existing = await db.execute(
        select(ServiceAccount).where(ServiceAccount.name == request.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Service account '{request.name}' already exists")

    # Create service account
    account = ServiceAccount(
        name=request.name,
        description=request.description,
    )
    db.add(account)

    # Generate API key
    api_key_value = generate_api_key()
    api_key = APIKey(
        name=f"{request.name}-default",
        key_hash=hash_api_key(api_key_value),
        key_prefix=get_key_prefix(api_key_value),
        can_write=1,
        can_read=1,
    )
    db.add(api_key)

    await db.commit()
    await db.refresh(account)
    await db.refresh(api_key)

    return CreateServiceAccountResponse(
        service_account_id=account.id,
        name=account.name,
        api_key=api_key_value,
        key_prefix=api_key.key_prefix,
        message="Service account created. Store the API key securely - it won't be shown again.",
    )


@router.post("/keys", response_model=IssueKeyResponse)
async def issue_key(
    request: IssueKeyRequest,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_master_key),
):
    """Issue a new API key for a service account."""
    # Find service account
    result = await db.execute(
        select(ServiceAccount).where(ServiceAccount.name == request.service_account_name)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail=f"Service account '{request.service_account_name}' not found")

    # Generate key
    api_key_value = generate_api_key()
    api_key = APIKey(
        name=request.key_name,
        key_hash=hash_api_key(api_key_value),
        key_prefix=get_key_prefix(api_key_value),
        can_write=1 if request.can_write else 0,
        can_read=1 if request.can_read else 0,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return IssueKeyResponse(
        id=api_key.id,
        name=api_key.name,
        api_key=api_key_value,
        key_prefix=api_key.key_prefix,
        service_account=account.name,
    )


@router.get("/keys", response_model=dict)
async def list_keys(
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_master_key),
):
    """List all API keys."""
    result = await db.execute(
        select(APIKey).order_by(APIKey.created_at)
    )
    keys = result.scalars().all()

    return {
        "keys": [
            APIKeyInfo(
                id=k.id,
                name=k.name,
                key_prefix=k.key_prefix,
                can_write=bool(k.can_write),
                can_read=bool(k.can_read),
                created_at=k.created_at,
                last_used_at=k.last_used_at,
                revoked=bool(k.revoked),
            )
            for k in keys
        ]
    }


@router.delete("/keys/{key_id}")
async def revoke_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_master_key),
):
    """Revoke an API key."""
    result = await db.execute(
        select(APIKey).where(APIKey.id == key_id)
    )
    key = result.scalar_one_or_none()

    if not key:
        raise HTTPException(status_code=404, detail="API key not found")

    key.revoked = 1
    key.revoked_at = datetime.now(timezone.utc)
    await db.commit()

    return {"message": f"API key {key.key_prefix}... revoked"}


# ============================================================================
# Retention & Maintenance
# ============================================================================

class RetentionStats(BaseModel):
    """Statistics about log retention."""
    total_logs: int
    logs_to_delete: int
    oldest_log: Optional[datetime]
    retention_days: int


@router.get("/retention/stats", response_model=RetentionStats)
async def get_retention_stats(
    retention_days: int = Query(None, description="Override default retention days"),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_master_key),
):
    """Get statistics about logs that would be deleted by retention policy."""
    days = retention_days or settings.LOG_RETENTION_DAYS
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Total logs
    total_result = await db.execute(select(func.count(LogEntry.id)))
    total = total_result.scalar()

    # Logs to delete
    delete_result = await db.execute(
        select(func.count(LogEntry.id)).where(LogEntry.timestamp < cutoff)
    )
    to_delete = delete_result.scalar()

    # Oldest log
    oldest_result = await db.execute(
        select(func.min(LogEntry.timestamp))
    )
    oldest = oldest_result.scalar()

    return RetentionStats(
        total_logs=total,
        logs_to_delete=to_delete,
        oldest_log=oldest,
        retention_days=days,
    )


@router.post("/retention/cleanup")
async def run_retention_cleanup(
    retention_days: int = Query(None, description="Override default retention days"),
    dry_run: bool = Query(True, description="If true, only report what would be deleted"),
    batch_size: int = Query(1000, ge=100, le=10000, description="Batch size for deletion"),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_master_key),
):
    """
    Delete logs older than retention period.

    By default runs in dry_run mode. Set dry_run=false to actually delete.
    Deletes in batches to avoid long-running transactions.
    """
    days = retention_days or settings.LOG_RETENTION_DAYS
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Count logs to delete
    count_result = await db.execute(
        select(func.count(LogEntry.id)).where(LogEntry.timestamp < cutoff)
    )
    total_to_delete = count_result.scalar()

    if dry_run:
        return {
            "dry_run": True,
            "retention_days": days,
            "cutoff_date": cutoff.isoformat(),
            "logs_to_delete": total_to_delete,
            "message": "Set dry_run=false to actually delete logs",
        }

    # Delete in batches
    deleted = 0
    while True:
        # Get batch of IDs to delete
        batch_result = await db.execute(
            select(LogEntry.id)
            .where(LogEntry.timestamp < cutoff)
            .limit(batch_size)
        )
        ids = [row[0] for row in batch_result.fetchall()]

        if not ids:
            break

        # Delete events first (foreign key)
        await db.execute(
            delete(LogEvent).where(LogEvent.log_entry_id.in_(ids))
        )

        # Delete logs
        await db.execute(
            delete(LogEntry).where(LogEntry.id.in_(ids))
        )

        await db.commit()
        deleted += len(ids)

    # Also clean up old spans
    span_count_result = await db.execute(
        select(func.count(Span.id)).where(Span.start_time < cutoff)
    )
    spans_to_delete = span_count_result.scalar()

    if spans_to_delete > 0:
        await db.execute(
            delete(Span).where(Span.start_time < cutoff)
        )
        await db.commit()

    return {
        "dry_run": False,
        "retention_days": days,
        "cutoff_date": cutoff.isoformat(),
        "logs_deleted": deleted,
        "spans_deleted": spans_to_delete,
        "message": f"Retention cleanup complete",
    }


@router.get("/stats")
async def get_admin_stats(
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_master_key),
):
    """Get overall database statistics."""
    # Log count
    log_count_result = await db.execute(select(func.count(LogEntry.id)))
    log_count = log_count_result.scalar()

    # Event count
    event_count_result = await db.execute(select(func.count(LogEvent.id)))
    event_count = event_count_result.scalar()

    # Span count
    span_count_result = await db.execute(select(func.count(Span.id)))
    span_count = span_count_result.scalar()

    # Service account count
    account_count_result = await db.execute(select(func.count(ServiceAccount.id)))
    account_count = account_count_result.scalar()

    # API key count
    key_count_result = await db.execute(select(func.count(APIKey.id)))
    key_count = key_count_result.scalar()

    # Date range
    oldest_result = await db.execute(select(func.min(LogEntry.timestamp)))
    oldest = oldest_result.scalar()

    newest_result = await db.execute(select(func.max(LogEntry.timestamp)))
    newest = newest_result.scalar()

    return {
        "logs": log_count,
        "events": event_count,
        "spans": span_count,
        "service_accounts": account_count,
        "api_keys": key_count,
        "date_range": {
            "oldest": oldest.isoformat() if oldest else None,
            "newest": newest.isoformat() if newest else None,
        },
        "retention_days": settings.LOG_RETENTION_DAYS,
    }
