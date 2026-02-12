"""Background embedding pipeline for semantic search.

Polls for un-embedded log entries, batches them, and generates
embeddings via Artemis. Runs as an asyncio task within the
FastAPI lifespan — no additional services needed.

Loop prevention: never embeds logs from 'logr' or 'artemis' services.
Cost control: daily cap on total embeddings generated.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone, date
from typing import Optional, List, Tuple
from uuid import UUID

import httpx
from sqlalchemy import text

from app.config import settings
from app.database import async_session_maker

logger = logging.getLogger("logr.embeddings")

# Services to NEVER embed (loop prevention)
EXCLUDED_SERVICES = frozenset({"logr", "artemis"})

# Levels to skip (high volume, low search value)
EXCLUDED_LEVELS = frozenset({"debug"})

# Minimum message length worth embedding
MIN_MESSAGE_LENGTH = 20

# Batch size per cycle
BATCH_SIZE = 50

# Poll interval
POLL_INTERVAL_SECONDS = 30


class EmbeddingPipeline:
    """Background task that finds un-embedded logs and embeds them via Artemis."""

    def __init__(self):
        self.running = False
        self.daily_count = 0
        self.daily_date: Optional[date] = None
        self.total_embedded = 0
        self.total_errors = 0
        self.last_run: Optional[datetime] = None
        self.daily_cap = int(os.environ.get("EMBEDDING_DAILY_CAP", "50000"))

    async def start(self):
        """Start the background embedding loop."""
        if not settings.ARTEMIS_API_KEY:
            logger.info("ARTEMIS_API_KEY not set, embedding pipeline disabled")
            return

        self.running = True
        logger.info(
            "Embedding pipeline started (poll=%ds, batch=%d, cap=%d/day)",
            POLL_INTERVAL_SECONDS,
            BATCH_SIZE,
            self.daily_cap,
        )

        while self.running:
            try:
                await self._run_cycle()
            except Exception:
                self.total_errors += 1
                logger.exception("Embedding cycle error")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    def stop(self):
        """Signal the loop to stop."""
        self.running = False
        logger.info("Embedding pipeline stopping")

    def get_status(self) -> dict:
        """Return current pipeline status for admin endpoint."""
        return {
            "enabled": bool(settings.ARTEMIS_API_KEY),
            "running": self.running,
            "daily_count": self.daily_count,
            "daily_cap": self.daily_cap,
            "daily_date": str(self.daily_date) if self.daily_date else None,
            "total_embedded": self.total_embedded,
            "total_errors": self.total_errors,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "config": {
                "poll_interval_seconds": POLL_INTERVAL_SECONDS,
                "batch_size": BATCH_SIZE,
                "min_message_length": MIN_MESSAGE_LENGTH,
                "excluded_services": sorted(EXCLUDED_SERVICES),
                "excluded_levels": sorted(EXCLUDED_LEVELS),
                "embedding_model": settings.EMBEDDING_MODEL,
            },
        }

    async def _run_cycle(self):
        """One polling cycle: find eligible logs, embed them."""
        # Reset daily counter at midnight UTC
        today = datetime.now(timezone.utc).date()
        if self.daily_date != today:
            self.daily_count = 0
            self.daily_date = today

        # Check daily cap
        if self.daily_count >= self.daily_cap:
            return

        remaining = self.daily_cap - self.daily_count
        batch_limit = min(BATCH_SIZE, remaining)

        async with async_session_maker() as session:
            # Find un-embedded eligible logs
            rows = await self._get_eligible_logs(session, batch_limit)

            if not rows:
                self.last_run = datetime.now(timezone.utc)
                return

            ids = [row[0] for row in rows]
            texts = [row[1] for row in rows]

            # Call Artemis for embeddings
            embeddings = await self._get_embeddings_batch(texts)

            if not embeddings:
                self.total_errors += 1
                return

            # Write embeddings back to DB
            count = 0
            for log_id, embedding in zip(ids, embeddings):
                if embedding:
                    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
                    await session.execute(
                        text(
                            "UPDATE log_entries "
                            "SET embedding = :emb::vector, "
                            "    embedding_model = :model "
                            "WHERE id = :id"
                        ),
                        {
                            "emb": embedding_str,
                            "model": settings.EMBEDDING_MODEL,
                            "id": log_id,
                        },
                    )
                    count += 1

            await session.commit()

            self.daily_count += count
            self.total_embedded += count
            self.last_run = datetime.now(timezone.utc)
            logger.info(
                "Embedded %d logs (daily: %d/%d)", count, self.daily_count, self.daily_cap
            )

    async def _get_eligible_logs(
        self, session, limit: int
    ) -> List[Tuple[UUID, str]]:
        """Find logs that need embedding."""
        excluded_services = ",".join(f"'{s}'" for s in EXCLUDED_SERVICES)
        excluded_levels = ",".join(f"'{l}'" for l in EXCLUDED_LEVELS)

        result = await session.execute(
            text(f"""
                SELECT id, message
                FROM log_entries
                WHERE embedding IS NULL
                  AND service NOT IN ({excluded_services})
                  AND level NOT IN ({excluded_levels})
                  AND length(message) >= :min_length
                ORDER BY timestamp DESC
                LIMIT :limit
            """),
            {"min_length": MIN_MESSAGE_LENGTH, "limit": limit},
        )
        return result.fetchall()

    async def _get_embeddings_batch(
        self, texts: List[str]
    ) -> Optional[List[Optional[List[float]]]]:
        """Get embeddings for a batch of texts from Artemis."""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{settings.ARTEMIS_URL}/v1/embeddings",
                    headers={
                        "Authorization": f"Bearer {settings.ARTEMIS_API_KEY}"
                    },
                    json={
                        "input": texts,
                        "model": settings.EMBEDDING_MODEL,
                    },
                )
                response.raise_for_status()
                data = response.json()
                # OpenAI-compatible response: data["data"][i]["embedding"]
                return [item["embedding"] for item in data["data"]]
        except Exception:
            logger.exception("Artemis embedding request failed")
            return None


# Module-level singleton
pipeline = EmbeddingPipeline()
