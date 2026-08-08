"""
Social Router — Peer Pulse
==========================
"Investors with similar sector exposure to yours added these tickers this week."

Replaces the rarely-used Risk Metrics card with a collective-intelligence
surface that's defensible compliance-wise (observation of peer behavior, not
a recommendation) and uses data we already have.

How it works:
  1. Compute the current user's top sectors from their portfolio.
  2. Find PEER USERS — those whose portfolio overlaps in ≥3 of those sectors.
  3. From those peers, aggregate tickers added to portfolio OR watchlist in
     the last 7 days. Group by ticker, count unique adders.
  4. Privacy floor (k-anonymity):
       • need ≥5 peers in the cohort, else return nothing
       • need ≥2 distinct adders per ticker, else drop the ticker
  5. Strip out tickers the user already owns/watches (nothing to discover).
  6. Return top 10 by adder count.

Cache: per-user TTLCache, 1 hour. The aggregation is a few-Supabase-calls fan-
out; caching keeps the dashboard snappy.

Compliance shape:
  • Endpoint returns counts and percentages — never names other users.
  • Frontend labels the surface "Peer pulse · observation of peer activity",
    not "what investors like you are buying."
  • Disclaimer attached via with_disclaimer().
"""

from __future__ import annotations

import os
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional

from cachetools import TTLCache
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.nse_universe import TICKER_TO_META
from app.core.compliance import with_disclaimer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/social", tags=["social"])

# ---------------------------------------------------------------------------
# Supabase admin client — bypasses RLS for cross-user aggregation. Backend
# only; never exposed to a session.
# ---------------------------------------------------------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

_sb_admin = None
if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    try:
        from supabase import create_client
        _sb_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        logger.info("social router: supabase admin client initialized")
    except Exception as e:
        logger.error("social router: supabase init failed: %s", e)

# Per-user cache: 1 hour. The peer pulse doesn't change much within an hour
# and the aggregation costs us a few cross-user reads.
_cache: TTLCache = TTLCache(maxsize=500, ttl=60 * 60)

# Privacy thresholds.
MIN_COHORT_SIZE = 5      # need ≥5 peers before we surface anything
MIN_TICKER_ADDERS = 2    # need ≥2 distinct adders before we name a ticker
SECTOR_OVERLAP_MIN = 3   # peers share ≥3 top sectors with the user
LOOKBACK_DAYS = 7
MAX_ITEMS_RETURNED = 10


# ---------------------------------------------------------------------------
# Request / response
# ---------------------------------------------------------------------------
class PeerPulseRequest(BaseModel):
    user_id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _user_sectors(rows: list[dict]) -> set[str]:
    """Top sectors for a user's portfolio. Returns a SET so overlap math is
    cheap. Unknown-sector tickers are skipped (can't match a cohort on null)."""
    out: set[str] = set()
    for r in rows:
        t = (r.get("ticker") or "").upper()
        sector = TICKER_TO_META.get(t, {}).get("sector")
        if sector and sector != "Unknown":
            out.add(sector)
    return out


def _safe_select_all(table: str, columns: str) -> list[dict]:
    """Fetch all rows of a table via the admin client. Bypasses RLS — only
    safe because the result is processed in-memory and never sent back to the
    client without aggregation + k-anonymity filtering."""
    if _sb_admin is None:
        return []
    try:
        res = _sb_admin.table(table).select(columns).execute()
        return res.data or []
    except Exception as e:
        logger.warning("social: select all %s failed: %s", table, e)
        return []


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
@router.post("/peer-pulse")
async def peer_pulse(req: PeerPulseRequest):
    """Return tickers most-added in the last 7 days by users with similar
    sector exposure. Privacy-floor enforced; never identifies individuals.
    """
    if _sb_admin is None:
        # No backend admin client configured — return graceful empty payload.
        return with_disclaimer({
            "available": False,
            "reason": "service_unconfigured",
            "items": [],
            "cohort_size": 0,
        })

    user_id = (req.user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")

    cache_key = f"peer_pulse|{user_id}"
    if cache_key in _cache:
        return _cache[cache_key]

    # --- 1. The current user's portfolio + watchlist (to compute sectors and
    # to exclude items the user already owns/watches).
    try:
        my_port = _sb_admin.table("portfolio").select("ticker") \
            .eq("user_id", user_id).execute().data or []
        my_watch = _sb_admin.table("watchlist").select("ticker") \
            .eq("user_id", user_id).execute().data or []
    except Exception as e:
        logger.warning("social: fetching user data failed: %s", e)
        return with_disclaimer({
            "available": False, "reason": "fetch_failed",
            "items": [], "cohort_size": 0,
        })

    user_sectors = _user_sectors(my_port)
    if not user_sectors:
        # Empty portfolio — no cohort to match.
        payload = with_disclaimer({
            "available": False,
            "reason": "empty_portfolio",
            "items": [], "cohort_size": 0,
        })
        _cache[cache_key] = payload
        return payload

    user_owned = {(r.get("ticker") or "").upper() for r in my_port} | \
                 {(r.get("ticker") or "").upper() for r in my_watch}

    # --- 2. Build sector profiles for every other user.
    # NOTE: this is an O(N) scan across all portfolio rows. Fine for <10K
    # rows total; will need a materialized cohort table at scale.
    all_port = _safe_select_all("portfolio", "user_id, ticker")
    user_to_sectors: dict[str, set[str]] = defaultdict(set)
    for row in all_port:
        uid = row.get("user_id")
        if not uid or uid == user_id:
            continue
        sector = TICKER_TO_META.get((row.get("ticker") or "").upper(), {}).get("sector")
        if sector and sector != "Unknown":
            user_to_sectors[uid].add(sector)

    # --- 3. Cohort = users with ≥SECTOR_OVERLAP_MIN sector matches.
    peer_ids = {
        uid for uid, sectors in user_to_sectors.items()
        if len(sectors & user_sectors) >= SECTOR_OVERLAP_MIN
    }

    if len(peer_ids) < MIN_COHORT_SIZE:
        payload = with_disclaimer({
            "available": False,
            "reason": "small_cohort",
            "cohort_size": len(peer_ids),
            "min_cohort_size": MIN_COHORT_SIZE,
            "user_top_sectors": sorted(user_sectors)[:5],
            "items": [],
        })
        _cache[cache_key] = payload
        return payload

    # --- 4. Fetch recent adds from cohort. Use timestamp filter, then in-memory
    # filter by peer set (Supabase's `.in_("user_id", list)` has a length cap
    # that can bite for big cohorts; safer to filter client-side).
    cutoff = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).isoformat()
    try:
        recent_port = _sb_admin.table("portfolio") \
            .select("user_id, ticker, created_at") \
            .gte("created_at", cutoff).execute().data or []
        recent_watch = _sb_admin.table("watchlist") \
            .select("user_id, ticker, created_at") \
            .gte("created_at", cutoff).execute().data or []
    except Exception as e:
        logger.warning("social: recent adds query failed: %s", e)
        recent_port, recent_watch = [], []

    # --- 5. Aggregate per ticker. Track {portfolio: {users}, watchlist: {users}}
    # so we can show both signals and so the count = distinct adders (not row count).
    per_ticker: dict[str, dict] = defaultdict(lambda: {"port": set(), "watch": set()})
    for row in recent_port:
        if row.get("user_id") not in peer_ids:
            continue
        t = (row.get("ticker") or "").upper()
        if not t or t in user_owned:
            continue
        per_ticker[t]["port"].add(row["user_id"])
    for row in recent_watch:
        if row.get("user_id") not in peer_ids:
            continue
        t = (row.get("ticker") or "").upper()
        if not t or t in user_owned:
            continue
        per_ticker[t]["watch"].add(row["user_id"])

    # --- 6. Build items, enforce per-ticker k-anonymity.
    items = []
    cohort_size = len(peer_ids)
    for t, d in per_ticker.items():
        distinct = d["port"] | d["watch"]
        if len(distinct) < MIN_TICKER_ADDERS:
            continue
        meta = TICKER_TO_META.get(t, {})
        items.append({
            "ticker": t,
            "name": meta.get("name", t),
            "sector": meta.get("sector", "—"),
            "adders": len(distinct),
            "adders_pct": round(len(distinct) / cohort_size * 100),
            "portfolio_adds": len(d["port"]),
            "watchlist_adds": len(d["watch"]),
        })
    items.sort(key=lambda x: (-x["adders"], x["ticker"]))
    items = items[:MAX_ITEMS_RETURNED]

    payload = with_disclaimer({
        "available": True,
        "cohort_size": cohort_size,
        "lookback_days": LOOKBACK_DAYS,
        "user_top_sectors": sorted(user_sectors)[:5],
        "items": items,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    })
    _cache[cache_key] = payload
    return payload
