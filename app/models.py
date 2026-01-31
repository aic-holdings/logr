"""SQLAlchemy models for Logr."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Column, String, Text, DateTime, Integer, Index, JSON
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base

try:
    from pgvector.sqlalchemy import Vector
    PGVECTOR_AVAILABLE = True
except ImportError:
    PGVECTOR_AVAILABLE = False
    Vector = None

Base = declarative_base()


class LogEntry(Base):
    """A structured log entry from any service."""

    __tablename__ = "log_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Source identification
    service = Column(String(100), nullable=False, index=True)
    environment = Column(String(50), default="production", index=True)

    # Log level
    level = Column(String(20), nullable=False, index=True)  # debug/info/warn/error/fatal

    # Content
    message = Column(Text, nullable=False)
    context = Column(JSONB, default=dict)  # Flexible structured data

    # Correlation
    trace_id = Column(String(100), index=True)  # Cross-service correlation
    request_id = Column(String(100), index=True)  # Single request tracking
    user_id = Column(String(100), index=True)  # User attribution

    # Timestamps
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Semantic search (optional, populated async)
    embedding = Column(Vector(1536) if PGVECTOR_AVAILABLE else Text, nullable=True)

    __table_args__ = (
        Index("ix_log_entries_service_timestamp", "service", "timestamp"),
        Index("ix_log_entries_level_timestamp", "level", "timestamp"),
        Index("ix_log_entries_service_level", "service", "level"),
    )


class APIKey(Base):
    """API key for service authentication."""

    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)  # e.g., "taskr-bot", "artemis"
    description = Column(Text)

    # Key storage
    key_hash = Column(String(64), unique=True, nullable=False, index=True)
    key_prefix = Column(String(12), nullable=False)  # For display: "logr_abc123..."

    # Permissions
    can_write = Column(Integer, default=1)  # Can POST logs
    can_read = Column(Integer, default=1)   # Can GET/search logs
    can_admin = Column(Integer, default=0)  # Can manage keys

    # Status
    revoked = Column(Integer, default=0)
    revoked_at = Column(DateTime(timezone=True))

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_used_at = Column(DateTime(timezone=True))


class ServiceAccount(Base):
    """Service account for grouping API keys."""

    __tablename__ = "service_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
