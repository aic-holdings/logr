"""Authentication utilities for Logr."""
import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import APIKey
from app.config import settings


def generate_api_key() -> str:
    """Generate a new API key with logr_ prefix."""
    random_part = secrets.token_urlsafe(32)
    return f"logr_{random_part}"


def hash_api_key(key: str) -> str:
    """Hash an API key for storage."""
    return hashlib.sha256(key.encode()).hexdigest()


def get_key_prefix(key: str) -> str:
    """Get display prefix for an API key."""
    return key[:12] if len(key) >= 12 else key


async def verify_api_key(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> APIKey:
    """Verify API key from Authorization header."""
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header. Use: Bearer <api_key>"
        )

    key = auth_header[7:]
    key_hash = hash_api_key(key)

    result = await db.execute(
        select(APIKey).where(
            APIKey.key_hash == key_hash,
            APIKey.revoked == 0
        )
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Update last used
    api_key.last_used_at = datetime.now(timezone.utc)
    await db.commit()

    return api_key


async def verify_write_permission(
    api_key: APIKey = Depends(verify_api_key)
) -> APIKey:
    """Verify API key has write permission."""
    if not api_key.can_write:
        raise HTTPException(status_code=403, detail="API key does not have write permission")
    return api_key


async def verify_read_permission(
    api_key: APIKey = Depends(verify_api_key)
) -> APIKey:
    """Verify API key has read permission."""
    if not api_key.can_read:
        raise HTTPException(status_code=403, detail="API key does not have read permission")
    return api_key


async def verify_master_key(request: Request) -> bool:
    """Verify master API key for admin operations."""
    if not settings.MASTER_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Master API key not configured"
        )

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    provided_key = auth_header[7:]
    if not secrets.compare_digest(provided_key, settings.MASTER_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid master API key")

    return True
