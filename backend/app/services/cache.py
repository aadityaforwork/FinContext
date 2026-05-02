"""
Cache utility
=============
Thin wrapper around cachetools.TTLCache so every service uses the same factory.
Today, ad-hoc TTLCache instances are scattered across market_data.py, grounding.py,
data_ingestion.py, and the company_data router. New code should call `make_cache`.

Phase 1 keeps caches in-process (fine for a single uvicorn worker). When/if the
backend scales horizontally we'll swap the implementation here for Redis without
touching call sites.
"""

from cachetools import TTLCache

# Sensible defaults per data type — tune in one place, not at every call site.
DEFAULT_TTL_SECONDS = {
    "quote": 300,         # 5 min — live prices
    "history": 600,       # 10 min — OHLCV
    "indices": 180,       # 3 min — index values
    "overview": 600,      # 10 min — company overview
    "financials": 1800,   # 30 min — statements
    "ratios": 600,        # 10 min
    "shareholding": 3600, # 1 hour
    "news": 900,          # 15 min — news feeds
    "context": 600,       # 10 min — grounding context
    "fundamentals": 1800, # 30 min — generic fundamentals
}


def make_cache(maxsize: int, ttl_seconds: int) -> TTLCache:
    """Create a TTL-bounded in-memory cache."""
    return TTLCache(maxsize=maxsize, ttl=ttl_seconds)


def make_named_cache(kind: str, maxsize: int = 100) -> TTLCache:
    """Create a cache with a default TTL for a known data type.

    Raises KeyError on unknown `kind` so typos surface immediately rather than
    silently picking a wrong TTL.
    """
    return TTLCache(maxsize=maxsize, ttl=DEFAULT_TTL_SECONDS[kind])
