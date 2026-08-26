"""
Response Cache (stale-while-revalidate)
========================================
Shared in-memory cache for the heavy intelligence endpoints. Two windows:

  • FRESH window  (0 → fresh_ttl)   — return cached, no refresh.
  • STALE window  (fresh_ttl → max_ttl) — return cached IMMEDIATELY, kick off
                                          a background refresh so the next
                                          load is fresh again.
  • EXPIRED       (>max_ttl)        — treat as miss, recompute synchronously.

The frontend always gets a sub-second response in the FRESH and STALE windows.
The user only ever waits the full LLM time on a true miss (first load of the
day, or user explicitly hits "force refresh").

Key derivation is left to callers — they know what makes their request unique
(positions hash, watchlist hash, date, etc.).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

# Default windows. Endpoints can override per-call.
# Bumped 5/15 → 15/60 because LLM-driven endpoints don't change minute-by-minute
# and cold Render workers make blocking recomputes painful. The frontend now
# also keeps a localStorage mirror, so users routinely see <1s paint even
# across the 60-min stale boundary.
DEFAULT_FRESH_TTL_S = 15 * 60    # 15 min — return cached, no refresh
DEFAULT_MAX_TTL_S   = 60 * 60    # 60 min — return cached + refresh in bg

# Cap memory: at ~10 KB per entry, 500 entries ≈ 5 MB.
_MAX_ENTRIES = 500

# Each entry: { "value": <payload>, "stored_at": float, "refreshing": bool }
_store: dict[str, dict] = {}
# Track in-flight refreshes so we don't kick off duplicates.
_refreshing: set[str] = set()


def make_key(*parts: Any) -> str:
    """Deterministic cache key from arbitrary parts. Uses sha256 over a stable
    JSON encoding so dict ordering doesn't matter."""
    payload = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _evict_if_full() -> None:
    if len(_store) <= _MAX_ENTRIES:
        return
    # LRU-ish: drop the oldest 10%.
    by_age = sorted(_store.items(), key=lambda kv: kv[1]["stored_at"])
    for k, _ in by_age[: max(1, len(_store) // 10)]:
        _store.pop(k, None)


def get(key: str, max_ttl_s: int = DEFAULT_MAX_TTL_S) -> tuple[Any | None, str]:
    """Return (value, status) where status is one of:
        "fresh"   — value is recent (within fresh_ttl)
        "stale"   — value is old but usable (within max_ttl)
        "miss"    — no usable cached value

    Status is informational; callers decide whether to trigger a background
    refresh on "stale". The "fresh" vs "stale" boundary is decided by the
    caller's `fresh_ttl_s` arg in `serve()`.
    """
    entry = _store.get(key)
    if not entry:
        return None, "miss"
    age = time.time() - entry["stored_at"]
    if age > max_ttl_s:
        return None, "miss"
    return entry["value"], "stale"  # caller upgrades to "fresh" via serve()


def put(key: str, value: Any) -> None:
    _evict_if_full()
    _store[key] = {"value": value, "stored_at": time.time()}


def age_seconds(key: str) -> float | None:
    entry = _store.get(key)
    if not entry:
        return None
    return time.time() - entry["stored_at"]


async def serve(
    key: str,
    *,
    compute: Callable[[], Awaitable[Any]],
    fresh_ttl_s: int = DEFAULT_FRESH_TTL_S,
    max_ttl_s:   int = DEFAULT_MAX_TTL_S,
    force_refresh: bool = False,
) -> tuple[Any, str]:
    """Stale-while-revalidate driver. Returns (value, source) where source is:
        "fresh"   — served from cache, age < fresh_ttl
        "stale"   — served from cache, age between fresh_ttl and max_ttl, refresh kicked off
        "miss"    — computed synchronously (cache was missing or force_refresh=True)

    `compute` is an async callable producing the value. It's awaited only on a
    miss; on stale, it's wrapped in a fire-and-forget task so the response
    returns immediately.
    """
    if not force_refresh:
        cached, _status = get(key, max_ttl_s=max_ttl_s)
        if cached is not None:
            age = age_seconds(key) or 0
            if age < fresh_ttl_s:
                return cached, "fresh"
            # STALE — return cached, kick off background refresh (once).
            if key not in _refreshing:
                _refreshing.add(key)

                async def _refresh():
                    try:
                        value = await compute()
                        put(key, value)
                    except Exception as e:
                        logger.warning("background refresh failed for %s: %s", key, e)
                    finally:
                        _refreshing.discard(key)

                # Don't await — runs in background.
                try:
                    asyncio.create_task(_refresh())
                except RuntimeError:
                    # No running loop (sync context) — give up on background refresh.
                    _refreshing.discard(key)
            return cached, "stale"

    # MISS or force_refresh — compute synchronously.
    value = await compute()
    put(key, value)
    return value, "miss"


# ---------------------------------------------------------------------------
# Cross-worker tier
# ---------------------------------------------------------------------------
# Everything above this line is per-process. That is a real problem in prod:
# the dashboard's three heavy endpoints (news-feed, market-summary,
# morning-brief) each keep their own module-level TTLCache, and those die with
# the worker. On Render's free tier the instance sleeps after ~15 min idle, and
# any multi-worker or serverless deployment hands each process its own empty
# copy — so the 60-min TTL was close to decorative and nearly every real user
# session paid a full cold recompute (RSS fan-out + yfinance + a full LLM call).
#
# llm_cache is the existing shared tier (in-process TTL + SQLAlchemy row,
# already used for crew outputs). These helpers put the dashboard endpoints on
# it too. Both degrade to the in-process behaviour on any DB error, so a cache
# outage can never break a request — worst case we recompute exactly as before.
#
# NOTE: llm_cache's persistent half only actually persists when DATABASE_URL
# points at Postgres. Unset, app/db falls back to SQLite on an ephemeral disk
# and this tier is a no-op — see the deploy note in AGENTS.md.
_SHARED_PREFIX = "respcache:"


async def get_shared(key: str, max_ttl_s: int = DEFAULT_MAX_TTL_S) -> Any | None:
    """Two-tier read: in-process first, then the cross-worker llm_cache tier."""
    cached, _status = get(key, max_ttl_s=max_ttl_s)
    if cached is not None:
        return cached

    try:
        from app.services.llm import llm_cache

        row = await llm_cache.get(_SHARED_PREFIX + key)
    except Exception as e:
        logger.warning("shared cache read failed for %s: %s", key, e)
        return None

    if not isinstance(row, dict) or "v" not in row:
        return None
    value = row["v"]
    # Re-seed the in-process tier so later hits in this worker skip the DB
    # entirely. Age restarts here, which is intentional: it bounds how often a
    # warm worker re-reads a row it already has.
    put(key, value)
    return value


async def put_shared(key: str, value: Any, ttl_s: int = DEFAULT_MAX_TTL_S) -> None:
    """Write through to both tiers. Never raises."""
    put(key, value)
    try:
        from app.services.llm import llm_cache

        # Wrapped in {"v": ...} so non-dict payloads survive the JSON column.
        await llm_cache.set(_SHARED_PREFIX + key, {"v": value}, ttl_s)
    except Exception as e:
        logger.warning("shared cache write failed for %s: %s", key, e)


def stats() -> dict:
    """Diagnostic — peek at cache size + age distribution. Useful from admin
    endpoints to verify the cache is actually warming the way you expect."""
    now = time.time()
    ages = [now - e["stored_at"] for e in _store.values()]
    return {
        "entries": len(_store),
        "max_entries": _MAX_ENTRIES,
        "in_flight_refreshes": len(_refreshing),
        "age_seconds": {
            "min": round(min(ages), 1) if ages else None,
            "max": round(max(ages), 1) if ages else None,
            "avg": round(sum(ages) / len(ages), 1) if ages else None,
        },
    }


def clear() -> int:
    """Wipe the cache. Returns number of entries cleared. Admin use."""
    n = len(_store)
    _store.clear()
    _refreshing.clear()
    return n
