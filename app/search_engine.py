"""Ensemble search engine combining BM25 + vector + heuristics via RRF fusion.

Runs multiple retrieval signals in parallel and fuses results using
Reciprocal Rank Fusion (RRF) for better search quality than any
single signal alone.

Signals:
  - BM25: PostgreSQL tsvector/tsquery full-text search
  - Vector: pgvector cosine similarity via Artemis embeddings
  - Heuristic: level weighting + recency boost

Degrades gracefully when signals are unavailable.
"""
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger("logr.search_engine")


# ============================================================================
# BM25 Full-Text Search
# ============================================================================

async def bm25_search(
    db: AsyncSession,
    query: str,
    *,
    service: Optional[str] = None,
    level: Optional[str] = None,
    since: Optional[datetime] = None,
    limit: int = 50,
) -> List[Dict]:
    """
    Full-text search using PostgreSQL tsvector/tsquery.

    Uses websearch_to_tsquery for natural language query parsing
    and ts_rank_cd (cover density) for BM25-equivalent ranking.
    """
    conditions = ["search_vector IS NOT NULL"]
    params: Dict = {"limit": limit, "query": query}

    conditions.append(
        "search_vector @@ websearch_to_tsquery('english', :query)"
    )

    if service:
        conditions.append("service = :service")
        params["service"] = service
    if level:
        conditions.append("level = :level")
        params["level"] = level.lower()
    if since:
        conditions.append("timestamp >= :since")
        params["since"] = since

    where_clause = " AND ".join(conditions)

    sql = text(f"""
        SELECT id, service, level, message, timestamp, trace_id, error_type,
               ts_rank_cd(
                   search_vector,
                   websearch_to_tsquery('english', :query),
                   32
               ) AS bm25_score
        FROM log_entries
        WHERE {where_clause}
        ORDER BY bm25_score DESC
        LIMIT :limit
    """)

    result = await db.execute(sql, params)
    rows = result.fetchall()

    return [
        {
            "id": row.id,
            "service": row.service,
            "level": row.level,
            "message": row.message,
            "timestamp": row.timestamp,
            "trace_id": row.trace_id,
            "error_type": row.error_type,
            "bm25_score": float(row.bm25_score),
        }
        for row in rows
    ]


# ============================================================================
# Vector Similarity Search
# ============================================================================

async def vector_search(
    db: AsyncSession,
    query_embedding: List[float],
    *,
    service: Optional[str] = None,
    level: Optional[str] = None,
    since: Optional[datetime] = None,
    limit: int = 50,
) -> List[Dict]:
    """
    Vector similarity search using pgvector cosine distance.

    Returns results ranked by cosine similarity (1 - distance).
    """
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    conditions = ["embedding IS NOT NULL"]
    params: Dict = {"embedding": embedding_str, "limit": limit}

    if service:
        conditions.append("service = :service")
        params["service"] = service
    if level:
        conditions.append("level = :level")
        params["level"] = level.lower()
    if since:
        conditions.append("timestamp >= :since")
        params["since"] = since

    where_clause = " AND ".join(conditions)

    sql = text(f"""
        SELECT id, service, level, message, timestamp, trace_id, error_type,
               1 - (embedding <=> CAST(:embedding AS vector)) AS vector_score
        FROM log_entries
        WHERE {where_clause}
        ORDER BY embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
    """)

    result = await db.execute(sql, params)
    rows = result.fetchall()

    return [
        {
            "id": row.id,
            "service": row.service,
            "level": row.level,
            "message": row.message,
            "timestamp": row.timestamp,
            "trace_id": row.trace_id,
            "error_type": row.error_type,
            "vector_score": float(row.vector_score),
        }
        for row in rows
    ]


# ============================================================================
# Heuristic Scoring
# ============================================================================

LEVEL_WEIGHTS = {
    "fatal": 1.0,
    "error": 0.85,
    "warn": 0.5,
    "info": 0.3,
    "debug": 0.1,
}

RECENCY_HALF_LIFE_HOURS = 24.0


def compute_heuristic_score(
    level: str,
    timestamp: datetime,
    now: Optional[datetime] = None,
) -> float:
    """
    Heuristic score combining level severity and recency.

    Level weight (60%): errors/fatal rank higher than info/debug.
    Recency boost (40%): exponential decay with 24h half-life.

    Returns a float in [0, 1].
    """
    if now is None:
        now = datetime.now(timezone.utc)

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    level_score = LEVEL_WEIGHTS.get(level.lower(), 0.3)

    age_hours = max((now - timestamp).total_seconds() / 3600.0, 0.0)
    recency_score = 2.0 ** (-age_hours / RECENCY_HALF_LIFE_HOURS)

    return 0.6 * level_score + 0.4 * recency_score


def apply_heuristics(results: List[Dict], now: Optional[datetime] = None) -> List[Dict]:
    """Add heuristic_score to each result and sort by it descending."""
    for r in results:
        r["heuristic_score"] = compute_heuristic_score(
            r["level"], r["timestamp"], now
        )

    results.sort(key=lambda r: r["heuristic_score"], reverse=True)
    return results


# ============================================================================
# Reciprocal Rank Fusion (RRF)
# ============================================================================

DEFAULT_RRF_K = 60


def rrf_fusion(
    ranked_lists: Dict[str, List[Dict]],
    k: int = DEFAULT_RRF_K,
    limit: int = 20,
) -> List[Dict]:
    """
    Combine multiple ranked result lists using Reciprocal Rank Fusion.

    RRF score for document d:
        score(d) = SUM over each ranker i: 1 / (k + rank_i(d))

    k=60 is the standard constant from Cormack, Clarke, Buettcher (2009).

    Documents appearing in multiple ranked lists get boosted.
    """
    doc_scores: Dict[UUID, float] = {}
    doc_signals: Dict[UUID, Dict[str, float]] = {}
    doc_data: Dict[UUID, Dict] = {}

    for signal_name, results in ranked_lists.items():
        for rank_0, result in enumerate(results):
            doc_id = result["id"]
            rank_1 = rank_0 + 1
            contribution = 1.0 / (k + rank_1)

            doc_scores[doc_id] = doc_scores.get(doc_id, 0.0) + contribution

            if doc_id not in doc_signals:
                doc_signals[doc_id] = {}
            doc_signals[doc_id][signal_name] = contribution

            if doc_id not in doc_data:
                doc_data[doc_id] = result

    # Normalize to 0-1: max possible is len(ranked_lists) * 1/(k+1)
    max_possible = len(ranked_lists) * (1.0 / (k + 1))

    fused = []
    for doc_id, score in sorted(
        doc_scores.items(), key=lambda x: x[1], reverse=True
    ):
        entry = dict(doc_data[doc_id])
        entry["rrf_score"] = round(score, 6)
        entry["signals"] = doc_signals[doc_id]
        entry["similarity"] = (
            round(score / max_possible, 4) if max_possible > 0 else 0.0
        )
        fused.append(entry)

    return fused[:limit]


# ============================================================================
# Ensemble Search Orchestrator
# ============================================================================

async def ensemble_search(
    db: AsyncSession,
    query: str,
    query_embedding: Optional[List[float]],
    *,
    service: Optional[str] = None,
    level: Optional[str] = None,
    since: Optional[datetime] = None,
    limit: int = 20,
    rrf_k: int = DEFAULT_RRF_K,
) -> Tuple[List[Dict], Dict[str, bool]]:
    """
    Run ensemble search combining BM25 + vector + heuristics with RRF fusion.

    Degrades gracefully:
    - Artemis down: skip vector signal, BM25+heuristics still work
    - No search_vector yet: skip BM25, vector+heuristics still work
    - Both missing: caller should fall back to ILIKE text search

    Returns (fused_results, signals_used).
    """
    pool_size = min(limit * 3, 100)
    ranked_lists: Dict[str, List[Dict]] = {}
    signals_used: Dict[str, bool] = {
        "bm25": False,
        "vector": False,
        "heuristic": False,
    }

    # 1. BM25 full-text search
    try:
        bm25_results = await bm25_search(
            db, query, service=service, level=level, since=since, limit=pool_size
        )
        if bm25_results:
            ranked_lists["bm25"] = bm25_results
            signals_used["bm25"] = True
    except Exception:
        logger.debug("BM25 search unavailable", exc_info=True)

    # 2. Vector similarity search
    if query_embedding:
        try:
            vector_results = await vector_search(
                db,
                query_embedding,
                service=service,
                level=level,
                since=since,
                limit=pool_size,
            )
            if vector_results:
                ranked_lists["vector"] = vector_results
                signals_used["vector"] = True
        except Exception:
            logger.debug("Vector search unavailable", exc_info=True)

    # 3. Heuristic re-ranking of all candidates from other signals
    all_docs: Dict[UUID, Dict] = {}
    for signal_results in ranked_lists.values():
        for doc in signal_results:
            if doc["id"] not in all_docs:
                all_docs[doc["id"]] = doc

    if all_docs:
        heuristic_ranked = apply_heuristics(list(all_docs.values()))
        ranked_lists["heuristic"] = heuristic_ranked
        signals_used["heuristic"] = True

    # 4. RRF fusion
    if not ranked_lists:
        return [], signals_used

    fused = rrf_fusion(ranked_lists, k=rrf_k, limit=limit)
    return fused, signals_used
