"""
Persistent LLM / Agent response cache
=====================================
Two-tier cache:
  1. In-process TTLCache  (fast, free, per uvicorn worker)
  2. Postgres / SQLite via SQLAlchemy (shared across workers, survives restart)

Use this for full crew outputs (Deep Dive, Portfolio Intelligence, Narrative,
etc.) — NOT for raw yfinance fetches. Raw service calls are already cached
in-process by services/cache.py and don't justify a DB row each.

Why this layer exists: Supabase free is 500 MB. The single biggest waste of
that budget would be re-running a 15K-token Deep Dive crew on the same ticker
twice in a day. This cache prevents that.

Public API:
    await get(cache_key)                          -> dict | None
    await set(cache_key, payload, ttl_seconds, scope='global')
    await invalidate(cache_key)
    await purge_expired(limit=500)                -> int   (rows deleted)

All functions degrade to no-ops on DB error so a cache outage never breaks
agent execution — at worst we recompute.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.db import async_session
from app.db.models import LLMCache
from app.services.cache import make_cache

logger = logging.getLogger(__name__)

# In-process layer. Tuned small — DB layer is the source of truth across workers.
_inproc = make_cache(maxsize=512, ttl_seconds=600)

# Hard cap on cache rows. Once we cross this, set() also evicts oldest.
_MAX_ROWS = 10_000

# Probability that a set() call also opportunistically purges expired rows.
# 1/50 keeps amortized cost low while still cleaning regularly under load.
_PURGE_PROBABILITY = 0.02


async def get(cache_key: str) -> dict | None:
    """Return the cached payload if present and unexpired, else None."""
    if cache_key in _inproc:
        return _inproc[cache_key]

    try:
        async with async_session() as session:
            row = await session.get(LLMCache, cache_key)
            if row is None:
                return None
            if row.expires_at < datetime.now(timezone.utc):
                # Expired — delete lazily.
                await session.delete(row)
                await session.commit()
                return None
            payload = row.payload
            _inproc[cache_key] = payload
            return payload
    except Exception as e:
        logger.warning("llm_cache.get failed for %s: %s", cache_key, e)
        return None


async def set(cache_key: str, payload: dict, ttl_seconds: int, scope: str = "global") -> None:
    """Upsert a cache row. Idempotent."""
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    _inproc[cache_key] = payload

    try:
        async with async_session() as session:
            existing = await session.get(LLMCache, cache_key)
            if existing is None:
                session.add(LLMCache(
                    cache_key=cache_key,
                    payload=payload,
                    scope=scope,
                    expires_at=expires_at,
                ))
            else:
                existing.payload = payload
                existing.scope = scope
                existing.expires_at = expires_at
            await session.commit()
    except Exception as e:
        logger.warning("llm_cache.set failed for %s: %s", cache_key, e)
        return

    # Opportunistic eviction — keeps the table within budget without a separate worker.
    if random.random() < _PURGE_PROBABILITY:
        try:
            await purge_expired()
            await _enforce_size_cap()
        except Exception as e:
            logger.warning("llm_cache opportunistic purge failed: %s", e)


async def invalidate(cache_key: str) -> None:
    """Drop a single key from both layers."""
    _inproc.pop(cache_key, None)
    try:
        async with async_session() as session:
            row = await session.get(LLMCache, cache_key)
            if row is not None:
                await session.delete(row)
                await session.commit()
    except Exception as e:
        logger.warning("llm_cache.invalidate failed for %s: %s", cache_key, e)


async def purge_expired(limit: int = 500) -> int:
    """Delete up to `limit` expired rows. Returns the row count deleted."""
    now = datetime.now(timezone.utc)
    try:
        async with async_session() as session:
            stmt = (
                select(LLMCache.cache_key)
                .where(LLMCache.expires_at < now)
                .limit(limit)
            )
            keys = (await session.execute(stmt)).scalars().all()
            if not keys:
                return 0
            await session.execute(delete(LLMCache).where(LLMCache.cache_key.in_(keys)))
            await session.commit()
            return len(keys)
    except Exception as e:
        logger.warning("llm_cache.purge_expired failed: %s", e)
        return 0


async def _enforce_size_cap() -> None:
    """If row count exceeds budget, delete the oldest entries."""
    try:
        async with async_session() as session:
            count_stmt = select(LLMCache.cache_key).limit(_MAX_ROWS + 1)
            rows_seen = len((await session.execute(count_stmt)).scalars().all())
            if rows_seen <= _MAX_ROWS:
                return
            # Over budget — drop the 100 oldest.
            oldest_stmt = (
                select(LLMCache.cache_key)
                .order_by(LLMCache.created_at.asc())
                .limit(100)
            )
            keys = (await session.execute(oldest_stmt)).scalars().all()
            if keys:
                await session.execute(delete(LLMCache).where(LLMCache.cache_key.in_(keys)))
                await session.commit()
                logger.info("llm_cache size cap: evicted %d oldest rows", len(keys))
    except Exception as e:
        logger.warning("llm_cache.enforce_size_cap failed: %s", e)


# ---------------------------------------------------------------------------
# Key helpers — keep keying logic in one place so we don't get key-format drift
# ---------------------------------------------------------------------------
def make_key(prefix: str, *parts: object) -> str:
    """Build a deterministic cache key. e.g. make_key('deep_dive', 'RELIANCE', '2025-05-01')."""
    return ":".join([prefix, *(str(p) for p in parts)])
