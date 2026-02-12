"""Database connection and session management."""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.config import settings

# Handle Railway's postgres:// vs postgresql://
database_url = settings.DATABASE_URL
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif database_url.startswith("postgresql://") and "+asyncpg" not in database_url:
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(
    database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    """Dependency for getting database sessions."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Initialize database tables."""
    from app.models import Base

    async with engine.begin() as conn:
        # Create pgvector extension if available
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        except Exception:
            pass  # Extension might not be available

        await conn.run_sync(Base.metadata.create_all)

        # Full-text search: add tsvector column if missing (idempotent)
        await conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'log_entries' AND column_name = 'search_vector'
                ) THEN
                    ALTER TABLE log_entries ADD COLUMN search_vector tsvector;
                END IF;
            END $$;
        """))

        # GIN index for fast full-text search
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_log_entries_search_vector
            ON log_entries USING gin(search_vector);
        """))

        # Trigger to auto-populate search_vector on INSERT/UPDATE
        await conn.execute(text("""
            CREATE OR REPLACE FUNCTION log_entries_search_vector_update() RETURNS trigger AS $$
            BEGIN
                NEW.search_vector :=
                    setweight(to_tsvector('english', COALESCE(NEW.message, '')), 'A') ||
                    setweight(to_tsvector('english', COALESCE(NEW.service, '')), 'B') ||
                    setweight(to_tsvector('english', COALESCE(NEW.error_type, '')), 'B') ||
                    setweight(to_tsvector('english', COALESCE(NEW.error_message, '')), 'C');
                RETURN NEW;
            END
            $$ LANGUAGE plpgsql;
        """))

        await conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_trigger WHERE tgname = 'trg_log_entries_search_vector'
                ) THEN
                    CREATE TRIGGER trg_log_entries_search_vector
                    BEFORE INSERT OR UPDATE OF message, service, error_type, error_message
                    ON log_entries
                    FOR EACH ROW
                    EXECUTE FUNCTION log_entries_search_vector_update();
                END IF;
            END $$;
        """))

        # Backfill existing rows that don't have search_vector yet
        await conn.execute(text("""
            UPDATE log_entries
            SET search_vector =
                setweight(to_tsvector('english', COALESCE(message, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(service, '')), 'B') ||
                setweight(to_tsvector('english', COALESCE(error_type, '')), 'B') ||
                setweight(to_tsvector('english', COALESCE(error_message, '')), 'C')
            WHERE search_vector IS NULL;
        """))
