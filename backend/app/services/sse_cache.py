"""
SSE stale-while-revalidate cache
================================
Every heavy generation endpoint in this app is an SSE stream that emits a few
`step` events and exactly one `result` event. They all want the same caching
behaviour, so it lives here once instead of being copy-pasted per router.

Three tiers, checked in order:

  1. **In-process** (`services.response_cache`) — a dict in this uvicorn
     worker. Sub-millisecond, but dies with the worker and isn't shared
     between workers.
  2. **Persistent** (`services.llm_cache` → Postgres/SQLite) — survives a
     Render restart and is shared across workers. Costs one indexed PK
     lookup (~10-30 ms), which is nothing next to a 60-second regeneration.
  3. **Miss** — drive the real generator, stream it through, then write the
     final `result` event into BOTH tiers on the way out.

Within tier 1/2 there are two windows:

  * FRESH  (age < fresh_ttl_s) — replay the cached result, do nothing else.
  * STALE  (fresh_ttl_s ≤ age < max_ttl_s) — replay the cached result
    immediately AND kick off a background regeneration so the next visitor
    gets a fresh one. The user never waits on it.

Net effect: a user pays the full generation cost once per ticker per window;
every visit after that paints in well under a second.

Usage:

    return StreamingResponse(
        sse_cache.cached_sse_stream(
            deep_dive_generator(ticker),          # NOT yet iterated
            cache_key=...,
            persist_key=...,
        ),
        media_type="text/event-stream",
    )

`inner_generator` MUST be a freshly-created async generator. On a fresh hit we
close it without iterating (so none of its yfinance/LLM work ever starts); on a
stale hit we hand it to a background task.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
from typing import Any, AsyncIterator, Callable

from app.services import llm_cache, response_cache

logger = logging.getLogger(__name__)

# Envelope marker so a persisted row can be told apart from a legacy raw
# payload written before this module existed.
_ENVELOPE_TAG = "__sse_cache_v1__"


def _wrap(payload: dict, stored_at: float) -> dict:
    return {_ENVELOPE_TAG: True, "stored_at": stored_at, "payload": payload}


def _unwrap(row: Any) -> tuple[dict | None, float | None]:
    """Return (payload, stored_at) from a persisted row, or (None, None)."""
    if not isinstance(row, dict):
        return None, None
    if row.get(_ENVELOPE_TAG):
        payload = row.get("payload")
        if isinstance(payload, dict):
            return payload, float(row.get("stored_at") or 0) or None
        return None, None
    # Legacy row (raw payload, no envelope) — usable, but we can't date it, so
    # treat it as freshly stored and let the TTL on the DB row bound it.
    return row, None


def _extract_result(chunk: Any) -> dict | None:
    """Pull the `result` payload out of a raw SSE chunk, if that's what it is."""
    if not isinstance(chunk, str) or not chunk.startswith("data: "):
        return None
    body = chunk[6:].strip()
    if not body or body == "[DONE]":
        return None
    try:
        parsed = json.loads(body)
    except (ValueError, json.JSONDecodeError):
        return None
    if isinstance(parsed, dict) and parsed.get("type") == "result":
        return parsed
    return None


async def _drain_into_cache(
    inner_generator: AsyncIterator,
    cache_key: str,
    persist_key: str | None,
    persist_ttl_s: int,
    scope: str,
) -> None:
    """Consume a generator to completion purely for its cache side-effect."""
    try:
        last = None
        async for chunk in inner_generator:
            found = _extract_result(chunk)
            if found is not None:
                last = found
        if last:
            await _store(last, cache_key, persist_key, persist_ttl_s, scope)
    except Exception as e:
        logger.warning("SSE background refresh failed for %s: %s", cache_key, e)
    finally:
        response_cache._refreshing.discard(cache_key)


async def _store(
    payload: dict,
    cache_key: str,
    persist_key: str | None,
    persist_ttl_s: int,
    scope: str,
) -> None:
    now = time.time()
    response_cache.put(cache_key, payload, stored_at=now)
    if persist_key:
        try:
            await llm_cache.set(persist_key, _wrap(payload, now), persist_ttl_s, scope)
        except Exception as e:
            # llm_cache already degrades to no-op internally; this is belt-and-braces
            # so a DB outage can never break a generation that already succeeded.
            logger.warning("SSE persist failed for %s: %s", persist_key, e)


async def _lookup(
    cache_key: str,
    persist_key: str | None,
    max_ttl_s: int,
) -> tuple[dict | None, float]:
    """Check tier 1 then tier 2. Returns (payload, age_seconds)."""
    cached, _ = response_cache.get(cache_key, max_ttl_s=max_ttl_s)
    if cached is not None:
        return cached, response_cache.age_seconds(cache_key) or 0.0

    if not persist_key:
        return None, 0.0

    try:
        row = await llm_cache.get(persist_key)
    except Exception as e:
        logger.warning("SSE persist lookup failed for %s: %s", persist_key, e)
        return None, 0.0

    payload, stored_at = _unwrap(row)
    if payload is None:
        return None, 0.0

    age = time.time() - stored_at if stored_at else 0.0
    if age > max_ttl_s:
        return None, 0.0

    # Hydrate the in-process tier so the next hit in this worker skips the DB.
    response_cache.put(cache_key, payload, stored_at=stored_at or time.time())
    return payload, age


async def cached_sse_stream(
    inner_generator: AsyncIterator,
    cache_key: str,
    *,
    force_refresh: bool = False,
    fresh_ttl_s: int,
    max_ttl_s: int,
    persist_key: str | None = None,
    persist_ttl_s: int | None = None,
    scope: str = "global",
    on_hit: Callable[[dict], dict] | None = None,
):
    """Wrap an SSE async-generator with stale-while-revalidate caching.

    `on_hit` is an optional transform applied to a cached payload before it is
    replayed — used to overlay live-but-cheap fields (e.g. the current price)
    onto an otherwise older analysis. It may be sync or async; anything that
    can block for more than a few ms belongs in the async form so it doesn't
    stall the event loop. If it raises, the untouched payload is served.
    """
    persist_ttl_s = persist_ttl_s if persist_ttl_s is not None else max_ttl_s

    if not force_refresh:
        cached, age = await _lookup(cache_key, persist_key, max_ttl_s)
        if cached is not None:
            if on_hit is not None:
                try:
                    transformed = on_hit(cached)
                    if inspect.isawaitable(transformed):
                        transformed = await transformed
                    if isinstance(transformed, dict):
                        cached = transformed
                except Exception as e:
                    logger.warning("SSE on_hit transform failed for %s: %s", cache_key, e)

            is_stale = age >= fresh_ttl_s
            label = (
                f"Loaded from cache ({int(age)}s old) — refreshing."
                if is_stale else "Loaded from cache."
            )
            yield f"data: {json.dumps({'type': 'step', 'message': label})}\n\n"
            yield f"data: {json.dumps(cached)}\n\n"
            yield "data: [DONE]\n\n"

            # Stale → refresh once in the background. The in-flight set stops
            # concurrent stale hits from firing duplicate regenerations.
            if is_stale and cache_key not in response_cache._refreshing:
                response_cache._refreshing.add(cache_key)
                try:
                    asyncio.create_task(
                        _drain_into_cache(
                            inner_generator, cache_key, persist_key, persist_ttl_s, scope
                        )
                    )
                    return  # generator handed off — don't close it below
                except RuntimeError:
                    response_cache._refreshing.discard(cache_key)

            # Not handed off — close it so its resources are released without
            # any of its work ever starting.
            aclose = getattr(inner_generator, "aclose", None)
            if aclose is not None:
                try:
                    await aclose()
                except Exception:
                    pass
            return

    # MISS or force_refresh — stream the real thing, capturing `result` on the
    # way past so the next request is instant.
    last_result = None
    async for chunk in inner_generator:
        found = _extract_result(chunk)
        if found is not None:
            last_result = found
        yield chunk

    if last_result is not None:
        await _store(last_result, cache_key, persist_key, persist_ttl_s, scope)


def make_key(*parts: Any) -> str:
    """Convenience re-export so callers only import this module."""
    return response_cache.make_key(*parts)
