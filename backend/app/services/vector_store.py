"""
Vector store
============
Thin wrapper around Supabase for the pgvector tables defined in
`supabase/migrations/002_pgvector_semantic_news.sql`.

Reads/writes the catalog (`stock_embeddings`) + the rolling news cache
(`news_embeddings`), and calls the `match_news_for_tickers` RPC for
semantic retrieval.

Requires backend env vars:
  SUPABASE_URL                — same as the frontend (NEXT_PUBLIC_SUPABASE_URL)
  SUPABASE_SERVICE_KEY        — service-role key (NOT the anon key — needed to
                                bypass RLS for writes). Get it from Supabase
                                Dashboard → Project Settings → API.

If either is missing, the module logs a warning and all calls become no-ops
(graceful degradation — the rest of the app keeps working without semantic
retrieval).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

_client = None
if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    try:
        from supabase import create_client
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        logger.info("Supabase vector_store client initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")
        _client = None
else:
    logger.warning(
        "SUPABASE_URL / SUPABASE_SERVICE_KEY not set — semantic retrieval disabled."
    )


def is_available() -> bool:
    return _client is not None


# ---------------------------------------------------------------------------
# Stock embeddings (catalog)
# ---------------------------------------------------------------------------
def upsert_stock_embeddings(rows: list[dict]) -> int:
    """Upsert stock embedding rows. Each row needs: ticker, name, sector,
    description, embedding (list[float]). Returns count upserted, or 0 if
    the client is unavailable."""
    if not _client or not rows:
        return 0
    try:
        _client.table("stock_embeddings").upsert(rows, on_conflict="ticker").execute()
        return len(rows)
    except Exception as e:
        logger.warning(f"upsert_stock_embeddings failed: {e}")
        return 0


def stock_embedding_count() -> int:
    """Quick sanity-check helper — how many stocks are embedded."""
    if not _client:
        return 0
    try:
        result = _client.table("stock_embeddings").select("ticker", count="exact").execute()
        return result.count or 0
    except Exception as e:
        logger.warning(f"stock_embedding_count failed: {e}")
        return 0


def news_embedding_count() -> int:
    """How many news rows are currently embedded."""
    if not _client:
        return 0
    try:
        result = _client.table("news_embeddings").select("id", count="exact").execute()
        return result.count or 0
    except Exception as e:
        logger.warning(f"news_embedding_count failed: {e}")
        return 0


def recent_news_samples(limit: int = 5) -> list[dict]:
    """Most recently embedded news items. Used by the health endpoint to
    eyeball whether the pipeline is alive."""
    if not _client:
        return []
    try:
        result = (
            _client.table("news_embeddings")
            .select("headline,scope,scope_ticker,source,created_at")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.warning(f"recent_news_samples failed: {e}")
        return []


# ---------------------------------------------------------------------------
# News embeddings (rolling cache)
# ---------------------------------------------------------------------------
def upsert_news_embeddings(rows: list[dict]) -> int:
    """Upsert news embedding rows. Each row needs: content_hash, headline,
    embedding, plus optional source/url/scope/scope_ticker/country/published_at.

    `content_hash` is unique — duplicates silently update existing rows
    instead of erroring.
    """
    if not _client or not rows:
        return 0
    try:
        _client.table("news_embeddings").upsert(rows, on_conflict="content_hash").execute()
        return len(rows)
    except Exception as e:
        logger.warning(f"upsert_news_embeddings failed: {e}")
        return 0


def prune_old_news(hours: int = 72) -> int:
    """Delete news embeddings older than N hours. Run periodically (or via
    cron) to keep the table small. Returns rows deleted (best-effort).
    """
    if not _client:
        return 0
    try:
        # Supabase Python client uses lt() with ISO strings — server clock is the source of truth.
        from datetime import datetime, timezone, timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        result = _client.table("news_embeddings").delete().lt("created_at", cutoff).execute()
        return len(result.data or [])
    except Exception as e:
        logger.warning(f"prune_old_news failed: {e}")
        return 0


# ---------------------------------------------------------------------------
# Semantic retrieval RPC
# ---------------------------------------------------------------------------
def ingest_news_items(items: list[dict]) -> int:
    """Take a flat list of news items, embed any that aren't already in the
    store, and upsert. Idempotent via content_hash.

    Each input item must include:
      - headline (str, required)
      - source   (str, optional)
      - snippet  (str, optional, used to enrich the embedding)
      - scope    ('stock_specific' | 'macro' | 'global')
      - scope_ticker (str, optional)
      - country  (str, optional)

    Designed to be called as a background task — does its own embedding so
    callers don't have to.
    """
    from app.services import embeddings as _embed
    if not _client or not items or not _embed.is_available():
        return 0

    # Build (text, item) pairs and dedup by content_hash so we don't pay to
    # embed the same headline twice within a single batch.
    seen_hashes: set[str] = set()
    pairs: list[tuple[str, str, dict]] = []  # (hash, embed_text, original_item)
    for it in items:
        headline = (it.get("headline") or "").strip()
        if not headline:
            continue
        snippet = (it.get("snippet") or "").strip()
        embed_text = f"{headline}. {snippet}" if snippet else headline
        h = _embed.content_hash(embed_text)
        if h in seen_hashes:
            continue
        seen_hashes.add(h)
        pairs.append((h, embed_text, it))

    if not pairs:
        return 0

    vecs = _embed.embed_batch([p[1] for p in pairs], chunk=50)

    rows: list[dict] = []
    for (h, _text, it), vec in zip(pairs, vecs):
        if vec is None:
            continue
        rows.append({
            "content_hash": h,
            "headline": (it.get("headline") or "").strip()[:500],
            "source": it.get("source"),
            "url": it.get("url"),
            "scope": it.get("scope", "macro"),
            "scope_ticker": it.get("scope_ticker"),
            "country": it.get("country"),
            "embedding": vec,
        })

    return upsert_news_embeddings(rows)


def match_news_for_tickers(
    tickers: list[str],
    match_count: int = 30,
    recency_hours: int = 48,
    match_threshold: float = 0.55,
) -> list[dict]:
    """Call the `match_news_for_tickers` Postgres function. Returns a list of
    annotated news items, each with `affected_ticker` (the user's stock that
    best matches) and `similarity` (cosine, 0-1, higher = closer).

    This is THE killer query — it surfaces news affecting a stock even when
    the headline never names it (e.g. "renewable subsidies" → TATAPOWER).
    """
    if not _client or not tickers:
        return []
    try:
        result = _client.rpc(
            "match_news_for_tickers",
            {
                "ticker_list": tickers,
                "match_count": match_count,
                "recency_hours": recency_hours,
                "match_threshold": match_threshold,
            },
        ).execute()
        return result.data or []
    except Exception as e:
        logger.warning(f"match_news_for_tickers failed: {e}")
        return []
