"""
Embeddings Router
=================
Admin endpoints for managing the pgvector embedding stores.

  POST /api/embeddings/backfill-stocks   → embeds every NSE_STOCKS entry once,
                                           enriched with AI-generated business
                                           description + theme tags. Re-runnable.
  POST /api/embeddings/prune-news        → deletes news embeddings >72h old
  GET  /api/embeddings/health            → quick status check (counts + provider)

These are intended to be called manually or via cron. They are protected by
an `X-Admin-Token` header — set ADMIN_TOKEN in env to enable. If unset, the
endpoints reject all calls.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException

from app.nse_universe import NSE_STOCKS
from app.services import ai_client, embeddings, vector_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/embeddings", tags=["embeddings"])

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")


# Allowed theme tags. Keeping a fixed vocabulary prevents the model from
# inventing dozens of unique tags that fragment the catalog. ~30 themes covers
# every NSE-listed business we care about.
_ALLOWED_TAGS = [
    "renewables", "thermal", "oil_gas", "nuclear", "crude_sensitive",
    "ev", "auto_demand", "auto_exports",
    "govt_psu", "defense", "capex", "infra",
    "exports", "fx_sensitive",
    "it_services", "semiconductors", "data_centers",
    "pharma", "hospitals", "specialty_chemicals",
    "banking", "nbfc", "insurance", "capital_markets",
    "fmcg", "agriculture", "retail",
    "metals", "cement",
    "real_estate", "logistics",
    "telecom", "aviation", "hospitality", "ports",
]


def _generate_descriptions_and_tags(stocks: list[dict]) -> dict[str, dict]:
    """Use the AI client (OpenAI gpt-4o-mini) to generate, for each stock:
       - a 2-3 sentence business description
       - 3-5 short theme tags from _ALLOWED_TAGS

    Batches of 10 stocks per call (~13 calls for 125 stocks). Cost is trivial
    (~$0.01 total on gpt-4o-mini). Returns {ticker: {description, tags}}.
    """
    if not ai_client.is_available():
        return {}

    BATCH = 10
    out: dict[str, dict] = {}
    tags_csv = ", ".join(_ALLOWED_TAGS)

    for i in range(0, len(stocks), BATCH):
        batch = stocks[i : i + BATCH]
        stock_list = "\n".join(
            f"- {s['ticker']}: {s['name']} ({s['sector']} sector)" for s in batch
        )
        task = (
            "For each NSE-listed Indian stock below, write:\n"
            "  1. A 2-3 sentence business description: WHAT the company does, its key segments, "
            "and what events/themes affect its revenue. Be specific (e.g. 'IT services exporter "
            "with 60% US revenue exposure' rather than 'tech company'). Plain English.\n"
            "  2. 3-5 short theme tags chosen ONLY from this allowed list:\n"
            f"    {tags_csv}\n"
            "Tags should reflect what would move the stock — sectoral exposures, business model, "
            "FX/govt sensitivities. Do NOT invent tags outside the allowed list.\n\n"
            f"STOCKS:\n{stock_list}\n\n"
            "Return JSON: { \"stocks\": [ { \"ticker\": str, \"description\": str, \"tags\": [str] }, ... ] }"
        )
        try:
            raw = ai_client.generate_json(task, max_tokens=2000, temperature=0.2)
            data = json.loads(raw)
            for s in data.get("stocks", []):
                t = (s.get("ticker") or "").upper()
                if not t:
                    continue
                desc = (s.get("description") or "").strip()[:600]
                tags = [tg for tg in (s.get("tags") or []) if tg in _ALLOWED_TAGS][:5]
                out[t] = {"description": desc, "tags": tags}
        except Exception as e:
            logger.warning(f"description+tag batch {i} failed: {e}")
            # Continue — partial results are fine; this method is idempotent on
            # the caller side (we just won't enrich the failed batch).
    return out


def _check_admin(token: str | None) -> None:
    """Reject if ADMIN_TOKEN isn't configured or the header doesn't match.
    Two layers: ADMIN_TOKEN env-var must be set, AND the request header must
    equal it. This prevents accidental exposure on free-tier hosts.
    """
    if not ADMIN_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="ADMIN_TOKEN not configured on the server. Set it in env to enable admin endpoints.",
        )
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid admin token.")


@router.get("/health")
async def embeddings_health(x_admin_token: str | None = Header(default=None)):
    """Quick status — provider availability + embedding counts + recent samples.

    Use this to verify the news pipeline is actually populating:
      - `news_embeddings_count` should grow as users load the dashboard.
      - `recent_news_samples` lets you eyeball that real headlines are landing.
    """
    _check_admin(x_admin_token)
    return {
        "embedding_provider": "openai" if embeddings.is_available() else None,
        "embedding_model": embeddings.EMBED_MODEL if embeddings.is_available() else None,
        "vector_store_available": vector_store.is_available(),
        "stock_embeddings_count": vector_store.stock_embedding_count(),
        "news_embeddings_count": vector_store.news_embedding_count(),
        "recent_news_samples": vector_store.recent_news_samples(limit=8),
        "nse_universe_size": len(NSE_STOCKS),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ticker-health")
async def ticker_health(x_admin_token: str | None = Header(default=None)):
    """Scan every NSE_STOCKS yfinance symbol and report which ones return no
    live price data right now. Use this to detect renames / delistings /
    Yahoo-side coverage drops before users notice "₹0" rows in their portfolio.

    Slow — makes ~125 yfinance calls. Run on demand, not on a hot path.
    Returns: {ok_count, broken_count, broken: [{ticker, yf_symbol, reason}], checked_at}
    """
    _check_admin(x_admin_token)
    import time
    import yfinance as yf
    from app.nse_universe import TICKER_TO_YF

    broken: list[dict] = []
    ok_count = 0
    for i, (ticker, yf_sym) in enumerate(TICKER_TO_YF.items()):
        try:
            info = yf.Ticker(yf_sym).fast_info
            price = float(info.last_price) if hasattr(info, "last_price") else None
            prev = float(info.previous_close) if hasattr(info, "previous_close") else None
            if not price or not prev:
                broken.append({"ticker": ticker, "yf_symbol": yf_sym, "reason": "no_price"})
            else:
                ok_count += 1
        except Exception as e:
            broken.append({"ticker": ticker, "yf_symbol": yf_sym, "reason": type(e).__name__})
        if i and i % 25 == 0:
            time.sleep(0.5)  # gentle pacing — don't hammer Yahoo

    return {
        "ok_count": ok_count,
        "broken_count": len(broken),
        "total": len(TICKER_TO_YF),
        "broken": broken,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/test-match")
async def test_match(
    tickers: list[str],
    match_count: int = 10,
    recency_hours: int = 72,
    match_threshold: float = 0.4,
    x_admin_token: str | None = Header(default=None),
):
    """Live semantic-match inspector. Body: a list of tickers. Returns the
    top news matches with similarity scores. Use this to verify the wedge
    works end-to-end (e.g. POST `["TATAPOWER"]` and check if news about
    'renewable subsidies' surfaces even though it doesn't name TATAPOWER).

    Defaults are intentionally loose (0.4 threshold, 72h window) so you see
    everything; the production endpoint uses 0.55 / 48h.
    """
    _check_admin(x_admin_token)
    if not vector_store.is_available():
        raise HTTPException(status_code=503, detail="Vector store not configured.")
    if not tickers:
        return {"matches": [], "note": "Provide at least one ticker in the request body."}

    matches = vector_store.match_news_for_tickers(
        tickers=[t.upper() for t in tickers],
        match_count=match_count,
        recency_hours=recency_hours,
        match_threshold=match_threshold,
    )

    # Score buckets — easier to read at a glance.
    buckets = {"very_strong": 0, "strong": 0, "moderate": 0, "weak": 0}
    for m in matches:
        s = m.get("similarity") or 0
        if s >= 0.75:
            buckets["very_strong"] += 1
        elif s >= 0.65:
            buckets["strong"] += 1
        elif s >= 0.55:
            buckets["moderate"] += 1
        else:
            buckets["weak"] += 1

    return {
        "tickers_queried": [t.upper() for t in tickers],
        "match_count": len(matches),
        "score_buckets": buckets,
        "matches": matches,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/backfill-stocks")
async def backfill_stocks(
    enrich: bool = True,
    x_admin_token: str | None = Header(default=None),
):
    """Backfill — embed every NSE_STOCKS entry and upsert to Supabase.

    When enrich=True (default), each stock gets:
      - an AI-generated business description (2-3 sentences)
      - 3-5 theme tags from a fixed allowed vocabulary

    The richer fingerprint dramatically improves pgvector retrieval — without
    it, the vector for "TATAPOWER" overlaps with every other power stock.

    Idempotent: re-running updates existing rows. Total cost: ~$0.02 for the
    AI enrichment + ~$0.0001 for the embeddings.

    Pass ?enrich=false to skip the AI step and use just name + sector (cheap,
    fast, lower quality — useful for development).
    """
    _check_admin(x_admin_token)

    if not embeddings.is_available():
        raise HTTPException(status_code=503, detail="Embeddings client not configured.")
    if not vector_store.is_available():
        raise HTTPException(status_code=503, detail="Vector store not configured.")

    # 1. Optionally enrich with AI-generated description + tags.
    enrichment: dict[str, dict] = {}
    if enrich and ai_client.is_available():
        enrichment = _generate_descriptions_and_tags(NSE_STOCKS)
        logger.info(f"Enriched {len(enrichment)}/{len(NSE_STOCKS)} stocks with description+tags")

    # 2. Build the embedding text. Richer = more discriminative vectors.
    texts: list[str] = []
    for s in NSE_STOCKS:
        en = enrichment.get(s["ticker"]) or {}
        desc = en.get("description") or f"{s['name']} — {s['sector']} sector"
        tags = en.get("tags") or []
        tags_part = f" Themes: {', '.join(tags)}." if tags else ""
        texts.append(
            f"{s['ticker']} ({s['name']}) — {s['sector']} sector. "
            f"{desc}{tags_part}"
        )

    # 3. Embed in batches.
    vecs = embeddings.embed_batch(texts, chunk=100)

    # 4. Build upsert rows.
    rows = []
    for stock, vec in zip(NSE_STOCKS, vecs):
        if vec is None:
            continue
        en = enrichment.get(stock["ticker"]) or {}
        rows.append({
            "ticker": stock["ticker"],
            "name": stock["name"],
            "sector": stock["sector"],
            "description": en.get("description") or f"{stock['name']} — {stock['sector']} sector",
            "tags": en.get("tags") or [],
            "embedding": vec,
        })

    upserted = vector_store.upsert_stock_embeddings(rows)
    return {
        "requested": len(NSE_STOCKS),
        "embedded": len(rows),
        "upserted": upserted,
        "enriched": len(enrichment),
        "skipped_embeddings": len(NSE_STOCKS) - len(rows),
        "enriched_pct": round(100 * len(enrichment) / max(len(NSE_STOCKS), 1), 1),
    }


@router.post("/prune-news")
async def prune_news(
    hours: int = 72,
    x_admin_token: str | None = Header(default=None),
):
    """Delete news embeddings older than `hours`. Default 72h. Run periodically
    to keep the table small."""
    _check_admin(x_admin_token)
    if not vector_store.is_available():
        raise HTTPException(status_code=503, detail="Vector store not configured.")
    deleted = vector_store.prune_old_news(hours=hours)
    return {"hours": hours, "deleted": deleted}
