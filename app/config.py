"""Configuration settings for Logr."""
import os
from functools import lru_cache


class Settings:
    """Application settings loaded from environment."""

    # Database
    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/logr"
    )

    # API Keys
    MASTER_API_KEY: str = os.environ.get("MASTER_API_KEY", "")

    # Encryption key for API keys (Fernet)
    ENCRYPTION_KEY: str = os.environ.get("ENCRYPTION_KEY", "")

    # Service info
    SERVICE_NAME: str = "logr"
    VERSION: str = "0.1.0"

    # Log retention (days, 0 = forever)
    LOG_RETENTION_DAYS: int = int(os.environ.get("LOG_RETENTION_DAYS", "90"))

    # Embedding model for semantic search
    EMBEDDING_MODEL: str = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
    EMBEDDING_DIMENSIONS: int = int(os.environ.get("EMBEDDING_DIMENSIONS", "1536"))

    # Artemis for embeddings (optional)
    ARTEMIS_API_KEY: str = os.environ.get("ARTEMIS_API_KEY", "")
    ARTEMIS_URL: str = os.environ.get("ARTEMIS_URL", "https://artemis.jettaintelligence.com")

    # Embedding pipeline
    EMBEDDING_DAILY_CAP: int = int(os.environ.get("EMBEDDING_DAILY_CAP", "50000"))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
