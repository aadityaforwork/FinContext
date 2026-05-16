"""
Onboarding Router
==================
One lean endpoint that powers the "First Insight" interstitial — the dopamine
hit a brand-new user sees right after picking their first stocks in the
OnboardingModal.

The goal: hand them a single, concrete, personalized sentence they can act on
within ~5 seconds of finishing the wizard. NOT a dashboard summary, NOT a
report card. ONE thing that says "this product knows my stuff already."

Selection priority (first hit wins so we always pick the highest-impact angle):

  1. EARNINGS_WITHIN_7D   — "{TICKER} reports earnings in {N} days"
                            (most urgent + most concrete)
  2. STRONG_MOVER         — "{TICKER} is {±X%} this week" for |change| >= 4%
  3. POLICY_HEADLINE      — A PIB/RBI item whose sector tag matches one of
                            the user's tickers' sectors
  4. SECTOR_CONCENTRATION — "{N}/{total} of your picks are in {sector}"
                            (always works as a fallback if portfolio has ≥3)
  5. WELCOME              — generic last-resort ("Tracking N stocks across S sectors")

Output is intentionally tiny — title + one sentence + optional CTA hint. The
frontend handles styling. Cached 5 min per (sorted ticker set, IST date) so a
user who refreshes during the interstitial doesn't trigger duplicate work.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from cachetools import TTLCache
from fastapi import APIRouter
from pydantic import BaseModel

from app.nse_universe import TICKER_TO_META
from app.services import grounding, policy_feeds, yf_safe

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

# 5-min cache keyed by (sorted-ticker-set, IST date). Two users with the same
# picks on the same day reuse the same insight — saves a couple of yfinance
# round-trips per impression.
_insight_cache: TTLCache = TTLCache(maxsize=200, ttl=300)


class FirstInsightRequest(BaseModel):
    tickers: list[str]


def _cache_key(tickers: list[str]) -> str:
    ist = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    key = ",".join(sorted({t.upper() for t in tickers if t}))
    return f"{ist.date().isoformat()}|{key}"


def _meta(ticker: str) -> dict:
    return TICKER_TO_META.get(ticker.upper(), {"name": ticker, "sector": "Unknown"})


@router.post("/first-insight")
async def first_insight(req: FirstInsightRequest) -> dict[str, Any]:
    """Return ONE personalized insight for the just-signed-up user.

    Always returns 200 with at least a fallback "welcome" payload — never
    blocks the onboarding flow on a backend hiccup.
    """
    tickers = [t.upper() for t in (req.tickers or []) if t]
    if not tickers:
        return {
            "kind": "welcome",
            "headline": "Welcome to FinContext",
            "body": "Add a few stocks above and we'll surface what matters today.",
            "cta": None,
        }

    cache_key = _cache_key(tickers)
    if cache_key in _insight_cache:
        return _insight_cache[cache_key]

    # ---------- 1. EARNINGS within 7 days ----------------------------------
    # We already have yf_safe-bounded _upcoming_earnings; checking <=8 picks
    # costs <2s in the worst case (each call is timeout-bounded at 5s,
    # parallelized via the executor's batching).
    earnings_hits: list[dict] = []
    for t in tickers[:10]:                            # cap so cold first-insight stays fast
        try:
            e = grounding._upcoming_earnings(t, max_days=7)
        except Exception:
            e = None
        if e:
            earnings_hits.append({"ticker": t, **e})
    earnings_hits.sort(key=lambda x: x.get("days_ahead", 99))
    if earnings_hits:
        top = earnings_hits[0]
        t = top["ticker"]
        days = top["days_ahead"]
        meta = _meta(t)
        when = "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"
        result = {
            "kind": "earnings",
            "ticker": t,
            "headline": f"{meta['name']} reports earnings {when}",
            "body": (
                f"{t} is on your list — earnings drop {when} ({top.get('date','')}). "
                "Open the Context Engine after the print to see how the market reads it."
            ),
            "cta": {"label": "Open dashboard", "view": "dashboard"},
        }
        _insight_cache[cache_key] = result
        return result

    # ---------- 2. STRONG MOVER today (>=4% absolute) ---------------------
    strong: list[dict] = []
    for t in tickers[:10]:
        try:
            snap = grounding._fetch_fast_snapshot(t)
        except Exception:
            snap = {}
        chg = snap.get("change_percent")
        if chg is not None and abs(chg) >= 4.0:
            strong.append({
                "ticker": t,
                "change_percent": chg,
                "current_price": snap.get("current_price"),
            })
    strong.sort(key=lambda x: abs(x["change_percent"]), reverse=True)
    if strong:
        top = strong[0]
        t = top["ticker"]
        chg = top["change_percent"]
        direction = "up" if chg > 0 else "down"
        meta = _meta(t)
        result = {
            "kind": "mover",
            "ticker": t,
            "headline": f"{meta['name']} is {direction} {abs(chg):.1f}% today",
            "body": (
                f"{t} moved hard today. We'll explain what drove it — and what to "
                "watch tomorrow — the moment you open the dashboard."
            ),
            "cta": {"label": "See what drove it", "view": "dashboard"},
        }
        _insight_cache[cache_key] = result
        return result

    # ---------- 3. POLICY/RBI headline matching user's sectors ------------
    user_sectors = {(_meta(t).get("sector") or "").lower() for t in tickers}
    user_sectors.discard("")
    user_sectors.discard("unknown")
    try:
        policy_items = policy_feeds.fetch_all_policy_items(limit_per_source=12) or []
    except Exception:
        policy_items = []
    for item in policy_items:
        item_sectors = [s.lower() for s in (item.get("affected_sectors") or [])]
        # Sub-string match in either direction (PIB sector strings differ from
        # our TICKER_TO_META sector strings, e.g. "Banking & Finance" vs "Banking")
        hit = any(
            any(us in i_s or i_s in us for us in user_sectors)
            for i_s in item_sectors
        )
        if hit:
            headline = (item.get("headline") or "").strip()
            src = item.get("source") or "PIB"
            if headline:
                result = {
                    "kind": "policy",
                    "headline": "Policy item matches your sectors",
                    "body": f"{headline} ({src}). We tagged it to your picks — open News Feed to see which.",
                    "cta": {"label": "Read in News Feed", "view": "dashboard"},
                }
                _insight_cache[cache_key] = result
                return result

    # ---------- 4. SECTOR concentration -----------------------------------
    sector_counts: dict[str, int] = {}
    for t in tickers:
        s = _meta(t).get("sector") or "Unknown"
        if s != "Unknown":
            sector_counts[s] = sector_counts.get(s, 0) + 1
    if sector_counts:
        top_sector, n = max(sector_counts.items(), key=lambda x: x[1])
        if n >= 2 and n >= max(2, len(tickers) // 3):
            result = {
                "kind": "concentration",
                "headline": f"{n} of your picks are in {top_sector}",
                "body": (
                    f"{n}/{len(tickers)} of your watchlist sits in {top_sector}. "
                    "AI Analysis will show how this concentration affects your risk profile."
                ),
                "cta": {"label": "Run AI Analysis", "view": "portfolio"},
            }
            _insight_cache[cache_key] = result
            return result

    # ---------- 5. Fallback: welcome with counts --------------------------
    result = {
        "kind": "welcome",
        "headline": f"Tracking {len(tickers)} {'stock' if len(tickers)==1 else 'stocks'}",
        "body": (
            f"Your watchlist is ready. We'll surface news, earnings, and policy events "
            f"affecting these {len(tickers)} names the moment you open the dashboard."
        ),
        "cta": {"label": "Open dashboard", "view": "dashboard"},
    }
    _insight_cache[cache_key] = result
    return result
