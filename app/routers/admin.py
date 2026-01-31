"""Admin API for master key operations."""
from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import APIKey, ServiceAccount
from app.auth import verify_master_key, generate_api_key, hash_api_key, get_key_prefix

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
