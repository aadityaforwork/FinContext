"""
Rate limiting for public, no-login routes
==========================================
Applies to endpoints meant to be called by anonymous/programmatic clients —
today that's the pre-trade-check scorecard and the raw context endpoint
(the two surfaces exposed to an eventual MCP server, see AGENTS.md /
STRATEGY.md for the broader context).

Deliberately NOT a hard auth gate: the web frontend calls these routes with
no credentials at all (no login required — matches the "demo mode" pattern
used elsewhere, e.g. portfolio_intelligence.py's news-feed). Requiring a key
would break that today. Instead this is a two-tier rate limit:

  anon  — no X-API-Key header (or keys aren't configured server-side at all).
          Low ceiling, bucketed per client IP. This is the fix for the "one
          enthusiastic agent user can get the shared egress IP throttled by
          Yahoo for everyone" abuse case.
  keyed — a valid X-API-Key matching one of settings.FINCONTEXT_API_KEYS.
          Higher ceiling, bucketed per key. Intended for the MCP server /
          other programmatic callers once keys are actually issued.

In-memory only (TTLCache, fixed window) — matches the caching style already
used throughout services/grounding.py. Resets on redeploy/restart and isn't
shared across workers; that's an acceptable trade for a first pass (same
caveat the in-process context/snapshot caches already carry). Revisit with a
shared store (Redis, or the Postgres table llm_cache.py already has a
precedent for) if this needs to hold across multiple workers/processes.
"""

from __future__ import annotations

import time

from fastapi import HTTPException, Request
from cachetools import TTLCache

from app.core.config import settings

# Fixed 60s window, bucketed by (identifier, window_id) — window_id is time
# floor-divided by _WINDOW_S, so each new window is a distinct cache key that
# starts at count 0 rather than a single per-identifier key whose TTL keeps
# getting pushed out on every write (which would never truly reset for a
# caller making even one request a minute, and could leave them stuck over
# the limit indefinitely). ttl=2*_WINDOW_S just bounds how long a stale
# window's entry lingers before eviction; it doesn't gate the limit itself.
_ANON_LIMIT = 30
_KEYED_LIMIT = 120
_WINDOW_S = 60

_anon_counts: TTLCache = TTLCache(maxsize=5000, ttl=_WINDOW_S * 2)
_keyed_counts: TTLCache = TTLCache(maxsize=1000, ttl=_WINDOW_S * 2)


def _window_id() -> int:
    return int(time.time() // _WINDOW_S)


def _client_ip(request: Request) -> str:
    # Render/Vercel sit behind a proxy — request.client.host would be the
    # proxy's address, not the caller's. Take the first hop of X-Forwarded-For
    # (the original client, by convention) when present.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def enforce(request: Request) -> None:
    """FastAPI dependency — raises 401/429, otherwise allows the request
    through and increments the caller's bucket for this window."""
    api_key = request.headers.get("x-api-key")
    window = _window_id()

    if api_key:
        if settings.FINCONTEXT_API_KEYS and api_key not in settings.FINCONTEXT_API_KEYS:
            raise HTTPException(status_code=401, detail="Invalid API key.")
        if settings.FINCONTEXT_API_KEYS:
            bucket_key = (api_key, window)
            count = _keyed_counts.get(bucket_key, 0) + 1
            _keyed_counts[bucket_key] = count
            if count > _KEYED_LIMIT:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded ({_KEYED_LIMIT}/min for this key). Try again shortly.",
                )
            return
        # A key was sent but none are configured server-side yet — fall
        # through to the anon bucket rather than silently ignoring it.

    ip = _client_ip(request)
    bucket_key = (ip, window)
    count = _anon_counts.get(bucket_key, 0) + 1
    _anon_counts[bucket_key] = count
    if count > _ANON_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit exceeded ({_ANON_LIMIT}/min without an API key). "
                "Try again shortly, or use an API key for a higher limit."
            ),
        )
