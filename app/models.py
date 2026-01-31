"""SQLAlchemy models for Logr - AI-friendly structured logging."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Column, String, Text, DateTime, Integer, Float, Index, ForeignKey, BigInteger
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship

try:
    from pgvector.sqlalchemy import Vector
    PGVECTOR_AVAILABLE = True
except ImportError:
    PGVECTOR_AVAILABLE = False
    Vector = None

Base = declarative_base()


class LogEntry(Base):
    """
    A structured log entry from any service.

    Follows OpenTelemetry semantic conventions for observability.
    Optimized for AI analysis with embeddings and rich context.
    """

    __tablename__ = "log_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # === Source Identification ===
    service = Column(String(100), nullable=False, index=True)
    environment = Column(String(50), default="production", index=True)
    host = Column(String(255))  # Hostname/container ID
    version = Column(String(50))  # Service version

    # === Log Level ===
    level = Column(String(20), nullable=False, index=True)  # debug/info/warn/error/fatal

    # === Content ===
    message = Column(Text, nullable=False)
    context = Column(JSONB, default=dict)  # Flexible structured data

    # === Trace Correlation (OpenTelemetry compatible) ===
    trace_id = Column(String(100), index=True)  # Cross-service correlation (W3C trace ID)
    span_id = Column(String(100), index=True)  # This operation's span
    parent_span_id = Column(String(100), index=True)  # Parent span for hierarchy

    # === Request Context ===
    request_id = Column(String(100), index=True)  # Single request tracking
    user_id = Column(String(100), index=True)  # User attribution
    session_id = Column(String(100), index=True)  # Session tracking

    # === Timing ===
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    duration_ms = Column(Float)  # Operation duration in milliseconds
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # === LLM-Specific Fields (for AI operations) ===
    model = Column(String(100), index=True)  # e.g., "claude-3-opus", "gpt-4"
    tokens_in = Column(Integer)  # Input tokens
    tokens_out = Column(Integer)  # Output tokens
    cost_usd = Column(Float)  # Computed cost in USD

    # === Error Details ===
    error_type = Column(String(100), index=True)  # Exception class name
    error_message = Column(Text)  # Error description
    stack_trace = Column(Text)  # Full stack trace

    # === Semantic Search ===
    embedding = Column(Vector(1536) if PGVECTOR_AVAILABLE else Text, nullable=True)
    embedding_model = Column(String(50))  # Model used for embedding

    # === Relationships ===
    events = relationship("LogEvent", back_populates="log_entry", cascade="all, delete-orphan")

    __table_args__ = (
        # Composite indexes for common queries
        Index("ix_log_entries_service_timestamp", "service", "timestamp"),
        Index("ix_log_entries_level_timestamp", "level", "timestamp"),
        Index("ix_log_entries_service_level", "service", "level"),
        Index("ix_log_entries_trace_timestamp", "trace_id", "timestamp"),
        Index("ix_log_entries_error_type_timestamp", "error_type", "timestamp"),
        Index("ix_log_entries_model_timestamp", "model", "timestamp"),
    )


class LogEvent(Base):
    """
    Large payload events associated with a log entry.

    Separates prompts, completions, tool calls, and other large payloads
    from the main log entry (per OpenTelemetry LLM Working Group recommendation).
    """

    __tablename__ = "log_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    log_entry_id = Column(UUID(as_uuid=True), ForeignKey("log_entries.id", ondelete="CASCADE"), nullable=False, index=True)

    # === Event Type ===
    event_type = Column(String(50), nullable=False, index=True)
    # Types: prompt, completion, tool_call, tool_result, retrieval, context, system_prompt

    # === Content ===
    content = Column(Text)  # The actual payload (prompt text, completion, etc.)
    content_type = Column(String(50), default="text/plain")  # MIME type

    # === Metadata ===
    metadata = Column(JSONB, default=dict)  # Event-specific metadata
    sequence = Column(Integer, default=0)  # Order within the log entry

    # === Timing ===
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    duration_ms = Column(Float)  # Event-specific duration

    # === Relationships ===
    log_entry = relationship("LogEntry", back_populates="events")

    __table_args__ = (
        Index("ix_log_events_entry_sequence", "log_entry_id", "sequence"),
        Index("ix_log_events_type_timestamp", "event_type", "timestamp"),
    )


class Span(Base):
    """
    Distributed tracing span for detailed operation tracking.

    Compatible with OpenTelemetry span model for integration
    with existing observability infrastructure.
    """

    __tablename__ = "spans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # === Identification ===
    trace_id = Column(String(100), nullable=False, index=True)
    span_id = Column(String(100), nullable=False, unique=True, index=True)
    parent_span_id = Column(String(100), index=True)

    # === Source ===
    service = Column(String(100), nullable=False, index=True)
    operation = Column(String(255), nullable=False)  # Operation name
    kind = Column(String(20), default="internal")  # client/server/producer/consumer/internal

    # === Timing ===
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True))
    duration_ms = Column(Float)

    # === Status ===
    status = Column(String(20), default="ok")  # ok/error/unset
    status_message = Column(Text)

    # === Attributes ===
    attributes = Column(JSONB, default=dict)  # Span attributes

    # === Resource ===
    resource = Column(JSONB, default=dict)  # Resource attributes (host, version, etc.)

    __table_args__ = (
        Index("ix_spans_trace_start", "trace_id", "start_time"),
        Index("ix_spans_service_operation", "service", "operation"),
    )


class APIKey(Base):
    """API key for service authentication."""

    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    service_account_id = Column(UUID(as_uuid=True), ForeignKey("service_accounts.id"), index=True)

    # Key storage
    key_hash = Column(String(64), unique=True, nullable=False, index=True)
    key_prefix = Column(String(12), nullable=False)

    # Permissions
    can_write = Column(Integer, default=1)
    can_read = Column(Integer, default=1)
    can_admin = Column(Integer, default=0)

    # Rate limiting
    rate_limit_per_minute = Column(Integer, default=1000)

    # Status
    revoked = Column(Integer, default=0)
    revoked_at = Column(DateTime(timezone=True))

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_used_at = Column(DateTime(timezone=True))

    # Relationships
    service_account = relationship("ServiceAccount", back_populates="api_keys")


class ServiceAccount(Base):
    """Service account for grouping API keys and tracking usage."""

    __tablename__ = "service_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text)

    # Usage tracking
    log_count = Column(BigInteger, default=0)
    last_log_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    api_keys = relationship("APIKey", back_populates="service_account", cascade="all, delete-orphan")


class RetentionPolicy(Base):
    """Log retention policy per service or globally."""

    __tablename__ = "retention_policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Scope (NULL = global default)
    service = Column(String(100), index=True)
    level = Column(String(20))  # Optional: different retention per level

    # Retention
    retention_days = Column(Integer, nullable=False, default=90)
    archive_to = Column(String(255))  # Optional: S3 bucket for archival

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_retention_service_level", "service", "level"),
    )
