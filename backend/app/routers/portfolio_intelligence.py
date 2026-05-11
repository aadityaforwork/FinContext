"""
Portfolio Intelligence Router
==============================
Grounded AI portfolio analysis. All claims reference real holdings data
(P&L, sector weights, concentration flags) from grounding.build_portfolio_context.
High-stakes output goes through a verifier pass.
"""

import asyncio
import json
import logging
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.compliance import with_disclaimer
from app.services import ai_client, grounding

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/intelligence", tags=["portfolio-intelligence"])


class PositionIn(BaseModel):
    ticker: str
    quantity: float
    buy_price: float


class IntelRequest(BaseModel):
    positions: list[PositionIn]


class MoversRequest(BaseModel):
    positions: list[PositionIn]


async def _intelligence_generator(raw_holdings: list[dict]):
    for msg in [
        "Fetching live prices for each holding...",
        "Computing P&L and sector allocation...",
        "Benchmarking each holding against sector peers...",
        "Running grounded AI strategist...",
        "Verifying claims against portfolio data...",
    ]:
        yield f"data: {json.dumps({'type':'step','message':msg})}\n\n"
        await asyncio.sleep(0.3)

    if not ai_client.is_available():
        yield f"data: {json.dumps({'type':'step','message':'ERROR: AI client not configured.'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    try:
        context = await asyncio.to_thread(grounding.build_portfolio_context, raw_holdings)
    except Exception as e:
        yield f"data: {json.dumps({'type':'error','message':f'Context build failed: {e}'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    task = (
        "Analyze this retail investor's portfolio. All signals must reference a specific "
        "holding's snapshot, weight_pct, or unrealized_pnl_pct from CONTEXT. Risks must "
        "cite CONTEXT.aggregate (sector_allocation, top_holding_pct, top_sector_pct, "
        "concentration_flag). Do NOT recommend specific tickers not in CONTEXT — instead "
        "return sector or factor suggestions. "
        "IMPORTANT: Use ONLY assessment language for `signal` — BULLISH/NEUTRAL/CAUTIOUS — "
        "never action language like buy/sell/hold. We are unregistered (not a SEBI RA) so "
        "all output must be educational stance, not advice."
    )
    schema = """{
  "portfolio_health_score": int (1-100) | null,
  "health_breakdown": {
    "diversification": int (1-100) | null,
    "quality": int (1-100) | null,
    "risk": int (1-100) | null,
    "momentum": int (1-100) | null
  },
  "holdings_verdicts": [
    { "ticker": str,
      "signal": "BULLISH" | "NEUTRAL" | "CAUTIOUS",
      "reason": { "text": str, "source": str },
      "confidence": int (1-100) }
  ],
  "top_risks": [ { "title": str, "description": { "text": str, "source": str } } ],
  "suggested_directions": [
    { "focus": str,               // e.g. "Defensive large-cap IT"
      "rationale": { "text": str, "source": str },
      "conviction": "HIGH" | "MEDIUM" }
  ],
  "confidence": "low" | "medium" | "high",
  "data_gaps": [ str, ... ]
}"""

    try:
        data = await asyncio.wait_for(
            asyncio.to_thread(ai_client.generate_grounded_json, task, context, schema, 2048),
            timeout=60,
        )
    except asyncio.TimeoutError:
        yield f"data: {json.dumps({'type':'error','message':'Timed out.'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    if not data:
        yield f"data: {json.dumps({'type':'error','message':'AI returned unparseable response.'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    verified = await asyncio.to_thread(ai_client.verify_claims, data, context, 1024)
    data = verified.get("verified", data)

    result = with_disclaimer({
        "type": "result",
        "portfolio_health_score": data.get("portfolio_health_score"),
        "health_breakdown": data.get("health_breakdown", {}),
        "holdings_verdicts": data.get("holdings_verdicts", []),
        "top_risks": data.get("top_risks", []),
        "suggested_directions": data.get("suggested_directions", []),
        "confidence": data.get("confidence", "low"),
        "data_gaps": data.get("data_gaps", []),
        "removed_by_verifier": verified.get("removed", []),
        "aggregate": context.get("aggregate", {}),
        "context_snapshot_at": context.get("generated_at"),
    })
    yield f"data: {json.dumps(result)}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/portfolio")
async def portfolio_intelligence(req: IntelRequest):
    if not req.positions:
        return {"error": "No holdings provided."}
    raw = [{"ticker": p.ticker, "quantity": p.quantity, "buy_price": p.buy_price} for p in req.positions]
    return StreamingResponse(_intelligence_generator(raw), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Context Engine — Why did my portfolio move today / What to watch tomorrow
# ---------------------------------------------------------------------------
async def _movers_generator(raw_holdings: list[dict]):
    for msg in [
        "Fetching NIFTY + sector index returns...",
        "Pulling today's headlines from India...",
        "Pulling overnight headlines from US / CN / EU / JP...",
        "Computing per-holding excess returns vs sector...",
        "Attributing today's moves to catalysts...",
        "Scanning for tomorrow's catalysts...",
    ]:
        yield f"data: {json.dumps({'type':'step','message':msg})}\n\n"
        await asyncio.sleep(0.25)

    if not ai_client.is_available():
        yield f"data: {json.dumps({'type':'error','message':'AI client not configured.'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    try:
        market_ctx = await asyncio.to_thread(grounding.build_market_context)
        movers_ctx = await asyncio.to_thread(grounding.build_movers_context, raw_holdings, market_ctx)
    except Exception as e:
        logger.exception("movers context build failed")
        yield f"data: {json.dumps({'type':'error','message':f'Context build failed: {e}'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    # -------- Today attribution --------
    today_task = (
        "For each holding in CONTEXT.holdings whose mover_bucket is 'strong_gainer' or "
        "'strong_loser', attribute today's price move to its most likely driver. "
        "Primary driver MUST be one of: 'stock_specific' (cite a {TICKER}_news[i]), "
        "'sector' (cite CONTEXT.market.sectors[i].sector + excess_return_today sign), "
        "'macro' (cite CONTEXT.india_headlines[i] or CONTEXT.market.indices), or "
        "'unexplained' (no supporting evidence in CONTEXT — add a data_gaps entry). "
        "Do NOT attribute flat movers. Keep attribution list to 1-2 items per holding, each "
        "with a weight_pct 1-100."
    )
    today_schema = """{
  "portfolio_return_today_pct": float | null,
  "top_positive_driver": { "text": str, "source": str } | null,
  "top_negative_driver": { "text": str, "source": str } | null,
  "movers": [
    {
      "ticker": str,
      "move_percent": float,
      "primary_driver": "stock_specific" | "sector" | "macro" | "unexplained",
      "attribution": [ { "text": str, "source": str, "weight_pct": int } ]
    }
  ],
  "confidence": "low" | "medium" | "high",
  "data_gaps": [ str, ... ]
}"""

    # Slim today CONTEXT: only actual movers, drop snippets, drop flat holdings.
    # Groq free tier is 12K TPM — full movers_ctx blows past that.
    def _slim_news(items, limit=2):
        return [
            {"id": n.get("id"), "source": n.get("source"), "headline": n.get("headline")}
            for n in (items or [])[:limit]
        ]

    mover_holdings = [
        {
            "ticker": h["ticker"],
            "sector": h.get("sector"),
            "change_percent_today": h.get("change_percent_today"),
            "sector_index_return_today": h.get("sector_index_return_today"),
            "excess_return_today": h.get("excess_return_today"),
            "mover_bucket": h.get("mover_bucket"),
            "news": _slim_news(h.get("news"), limit=2),
        }
        for h in movers_ctx.get("holdings", [])
        if h.get("mover_bucket") in ("strong_gainer", "strong_loser")
    ]

    today_input = {
        "portfolio_return_today_pct": movers_ctx.get("portfolio_return_today_pct"),
        "holdings": mover_holdings,
        "market": {
            "sectors": [
                {"sector": s.get("sector"), "change_percent": s.get("change_percent")}
                for s in movers_ctx.get("market", {}).get("sectors", [])
            ],
        },
        "india_headlines": _slim_news(market_ctx.get("india_headlines"), limit=5),
    }

    # -------- Tomorrow outlook --------
    tomorrow_task = (
        "Using ONLY CONTEXT.global_headlines (overnight world news) and CONTEXT.india_headlines "
        "(today's Indian macro news), identify 3-5 themes that may move the user's portfolio "
        "tomorrow. For each theme: cite the specific *_news[i] id, name which holdings or "
        "sectors in CONTEXT.holdings are likely affected and the direction (positive/negative), "
        "and briefly explain the transmission mechanism (e.g. crude up → OMCs negative, Fed dovish "
        "→ IT services positive). Only include themes where a holding or sector in CONTEXT is "
        "genuinely exposed. Do NOT speculate on themes not in CONTEXT."
    )
    tomorrow_schema = """{
  "themes": [
    {
      "theme": str,                                  // e.g. "Crude oil spike"
      "direction": "positive" | "negative" | "mixed",
      "affected_holdings": [ str ],                  // tickers from CONTEXT.holdings
      "affected_sectors": [ str ],
      "mechanism": { "text": str, "source": str },   // source cites a *_news[i] id
      "importance": "high" | "medium" | "low"
    }
  ],
  "overall_bias": "positive" | "negative" | "neutral",
  "confidence": "low" | "medium" | "high",
  "data_gaps": [ str, ... ]
}"""

    # Slim tomorrow CONTEXT: cap global to 2/country, drop snippets everywhere.
    slim_global = []
    per_country: dict[str, int] = {}
    for n in market_ctx.get("global_headlines", []):
        c = n.get("country") or "?"
        if per_country.get(c, 0) >= 2:
            continue
        per_country[c] = per_country.get(c, 0) + 1
        slim_global.append({
            "id": n.get("id"),
            "country": c,
            "source": n.get("source"),
            "headline": n.get("headline"),
        })

    tomorrow_input = {
        "holdings": [
            {"ticker": h["ticker"], "sector": h["sector"]}
            for h in movers_ctx.get("holdings", [])
        ],
        "sector_allocation_today": [
            {"sector": s.get("sector"), "change_percent": s.get("change_percent")}
            for s in movers_ctx.get("market", {}).get("sectors", [])
        ],
        "india_headlines": _slim_news(market_ctx.get("india_headlines"), limit=5),
        "global_headlines": slim_global,
    }

    # Short-circuit today call if nothing moved enough to attribute.
    async def _run_today():
        if not mover_holdings:
            return {"movers": [], "confidence": "high",
                    "data_gaps": ["No holding moved ≥1.5% today."]}
        return await asyncio.to_thread(
            ai_client.generate_grounded_json, today_task, today_input, today_schema, 2048
        )

    try:
        today_data, tomorrow_data = await asyncio.wait_for(
            asyncio.gather(
                _run_today(),
                asyncio.to_thread(ai_client.generate_grounded_json, tomorrow_task, tomorrow_input, tomorrow_schema, 2048),
            ),
            timeout=75,
        )
    except asyncio.TimeoutError:
        yield f"data: {json.dumps({'type':'error','message':'Context Engine timed out.'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    today_data = today_data or {}
    tomorrow_data = tomorrow_data or {}

    if mover_holdings:
        try:
            today_verified = await asyncio.to_thread(ai_client.verify_claims, today_data, today_input, 1024)
            today_data = today_verified.get("verified", today_data)
        except Exception as e:
            logger.warning("today verifier failed: %s", e)

    result = with_disclaimer({
        "type": "result",
        "portfolio_return_today_pct": movers_ctx.get("portfolio_return_today_pct"),
        "market_indices": movers_ctx.get("market", {}).get("indices", {}),
        "sector_returns": movers_ctx.get("market", {}).get("sectors", []),
        "today": {
            "top_positive_driver": today_data.get("top_positive_driver"),
            "top_negative_driver": today_data.get("top_negative_driver"),
            "movers": today_data.get("movers", []),
            "confidence": today_data.get("confidence", "low"),
            "data_gaps": today_data.get("data_gaps", []),
        },
        "tomorrow": {
            "themes": tomorrow_data.get("themes", []),
            "overall_bias": tomorrow_data.get("overall_bias", "neutral"),
            "confidence": tomorrow_data.get("confidence", "low"),
            "data_gaps": tomorrow_data.get("data_gaps", []),
        },
        "context_snapshot_at": movers_ctx.get("generated_at"),
    })
    yield f"data: {json.dumps(result)}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/movers")
async def portfolio_movers(req: MoversRequest):
    if not req.positions:
        return {"error": "No holdings provided."}
    raw = [{"ticker": p.ticker, "quantity": p.quantity, "buy_price": p.buy_price} for p in req.positions]
    return StreamingResponse(_movers_generator(raw), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Morning Brief — personalized "what matters for YOUR portfolio today"
# ---------------------------------------------------------------------------
from cachetools import TTLCache
from datetime import datetime, timezone

# Cached for 4 hours, keyed by content (date + holdings tickers + watchlist tickers).
# Two users with identical universes share the cached brief — saves AI cost dramatically.
_morning_brief_cache: TTLCache = TTLCache(maxsize=200, ttl=4 * 60 * 60)

# Sample portfolio used when a user has no holdings + empty watchlist (cold start).
# Lets the startup demo viewer see the value in <2 seconds without needing data.
_DEMO_HOLDINGS = [
    {"ticker": "INFY", "quantity": 10, "buy_price": 1500},
    {"ticker": "TCS",  "quantity": 5,  "buy_price": 3500},
    {"ticker": "RELIANCE", "quantity": 8,  "buy_price": 2400},
    {"ticker": "HDFCBANK", "quantity": 12, "buy_price": 1600},
    {"ticker": "TATAMOTORS", "quantity": 20, "buy_price": 600},
]
_DEMO_WATCHLIST = ["BAJFINANCE", "ITC", "ASIANPAINT"]


class MorningBriefRequest(BaseModel):
    positions: list[PositionIn] = []
    watchlist_tickers: list[str] = []
    force_refresh: bool = False  # bypass cache (used by frontend "Refresh" button)


def _brief_cache_key(positions: list[dict], watchlist: list[str]) -> str:
    # Date string makes cache invalidate at midnight UTC. Sorted tuples make key stable.
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    h_key = ",".join(sorted({(p.get("ticker") or "").upper() for p in positions if p.get("ticker")}))
    w_key = ",".join(sorted({t.upper() for t in watchlist if t}))
    return f"{today}|{h_key}|{w_key}"


@router.post("/morning-brief")
async def morning_brief(req: MorningBriefRequest):
    """Personalized 'what matters for YOUR portfolio today' brief.

    Returns 3-5 categorized bullets, each with cited source + soft-stance language
    (tailwind/headwind/watch — never buy/sell, since unregistered RA).
    """
    # Resolve demo mode for cold-start users
    demo_mode = not req.positions and not req.watchlist_tickers
    if demo_mode:
        raw_positions = _DEMO_HOLDINGS
        watchlist = _DEMO_WATCHLIST
    else:
        raw_positions = [
            {"ticker": p.ticker, "quantity": p.quantity, "buy_price": p.buy_price}
            for p in req.positions
        ]
        watchlist = list(req.watchlist_tickers)

    cache_key = _brief_cache_key(raw_positions, watchlist)
    if not req.force_refresh and cache_key in _morning_brief_cache:
        return _morning_brief_cache[cache_key]

    if not ai_client.is_available():
        return with_disclaimer({
            "demo_mode": demo_mode,
            "items": [],
            "error": "AI client not configured.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    try:
        context = await asyncio.to_thread(
            grounding.build_morning_brief_context, raw_positions, watchlist
        )
    except Exception as e:
        logger.exception("morning brief context build failed")
        return with_disclaimer({
            "demo_mode": demo_mode,
            "items": [],
            "error": f"Could not build context: {e}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    task = (
        "You are an analyst writing a personalized morning brief for an Indian retail investor. "
        "Generate 3-5 bullets that explain what matters TODAY for the user's specific universe "
        "(CONTEXT.holdings + CONTEXT.watchlist). Each bullet must reference a specific source id "
        "from CONTEXT (e.g. global_news[2], INFY_news[0], or sectors[i].sector). "
        "\n\n"
        "STRICT RULES:\n"
        "1. NEVER recommend buy/sell/hold. Use soft stance language: 'tailwind', 'headwind', "
        "'watch', 'neutral'. You are educational, not advisory.\n"
        "2. Each bullet's affected_tickers MUST be tickers that appear in CONTEXT.holdings or "
        "CONTEXT.watchlist. Do NOT mention other tickers.\n"
        "3. Prefer themes that connect a global/macro event to the user's specific holdings via "
        "sector or business model (e.g. US 10Y up → IT services headwind because they earn USD).\n"
        "4. Prioritize: stock-specific news for held tickers > sector moves > India macro > global macro.\n"
        "5. Keep each bullet's body under 220 characters. Headline under 80 characters.\n"
        "6. If the user has zero holdings (CONTEXT.user_universe.holdings_count=0), still produce "
        "general market-flavored bullets covering the watchlist + indices."
    )
    schema = """{
  "items": [
    {
      "category": "macro" | "sector" | "stock_specific" | "global" | "earnings",
      "headline": str,
      "body": { "text": str, "source": str },
      "affected_tickers": [ str ],
      "stance": "tailwind" | "headwind" | "watch" | "neutral"
    }
  ],
  "market_summary": { "text": str, "source": str } | null,
  "confidence": "low" | "medium" | "high",
  "data_gaps": [ str, ... ]
}"""

    try:
        data = await asyncio.wait_for(
            asyncio.to_thread(
                ai_client.generate_grounded_json, task, context, schema, 1024
            ),
            timeout=45,
        )
    except asyncio.TimeoutError:
        return with_disclaimer({
            "demo_mode": demo_mode,
            "items": [],
            "error": "Generation timed out.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    if not data:
        return with_disclaimer({
            "demo_mode": demo_mode,
            "items": [],
            "error": "AI returned unparseable response.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    # Validate affected_tickers against the user's actual universe — defense against
    # hallucinated symbols. Drop any ticker not in CONTEXT.
    universe = {h["ticker"] for h in context.get("holdings", [])} | {
        w["ticker"] for w in context.get("watchlist", [])
    }
    items = data.get("items") or []
    cleaned_items: list[dict] = []
    for it in items[:5]:
        affected = [t for t in (it.get("affected_tickers") or []) if t in universe]
        cleaned_items.append({
            "category": it.get("category", "macro"),
            "headline": (it.get("headline") or "").strip()[:120],
            "body": it.get("body") or {"text": "", "source": ""},
            "affected_tickers": affected,
            "stance": it.get("stance", "neutral"),
        })

    payload = with_disclaimer({
        "demo_mode": demo_mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": cleaned_items,
        "market_summary": data.get("market_summary"),
        "market_snapshot": {
            "indices": context.get("indices", {}),
            "sectors_top_3_movers": sorted(
                context.get("sectors", []),
                key=lambda s: abs(s.get("change_percent") or 0),
                reverse=True,
            )[:3],
        },
        "user_universe": context.get("user_universe", {}),
        "confidence": data.get("confidence", "low"),
        "data_gaps": data.get("data_gaps", []),
    })

    _morning_brief_cache[cache_key] = payload
    return payload


# ---------------------------------------------------------------------------
# News-Impact Feed — the USP. Every news item annotated with portfolio impact.
#
# This is the killer feature: instead of one daily brief, we annotate each
# news headline with which of the user's tickers it touches, in which direction,
# at what impact level, and why. That's what nobody else in the Indian market
# does on the front page.
# ---------------------------------------------------------------------------
_news_feed_cache: TTLCache = TTLCache(maxsize=200, ttl=60 * 60)  # 1 hour


class NewsFeedRequest(BaseModel):
    positions: list[PositionIn] = []
    watchlist_tickers: list[str] = []
    force_refresh: bool = False


def _news_feed_cache_key(positions: list[dict], watchlist: list[str]) -> str:
    # 1-hour bucket keeps the feed feeling live but avoids regen for every page load.
    bucket = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")
    h_key = ",".join(sorted({(p.get("ticker") or "").upper() for p in positions if p.get("ticker")}))
    w_key = ",".join(sorted({t.upper() for t in watchlist if t}))
    return f"{bucket}|{h_key}|{w_key}"


def _collect_candidate_news(context: dict) -> list[dict]:
    """Flatten all news available in the morning-brief context into a single list.

    Stock-specific news is guaranteed relevant (it's about a user's ticker) so
    we keep ALL of it. Macro/global are capped to keep token budget bounded.
    Final cap (90) is sized for ~50-stock universes on gpt-4o-mini's 128k context.
    """
    candidates: list[dict] = []

    # Per-holding ticker news — HIGHEST priority. Take all available.
    for h in context.get("holdings", []):
        for n in h.get("news", []):
            candidates.append({
                "id": n.get("id"),
                "headline": n.get("headline"),
                "source": n.get("source"),
                "scope": "stock_specific",
                "scope_ticker": h.get("ticker"),
            })

    # Per-watchlist ticker news — also guaranteed relevant.
    for w in context.get("watchlist", []):
        for n in w.get("news", []):
            candidates.append({
                "id": n.get("id"),
                "headline": n.get("headline"),
                "source": n.get("source"),
                "scope": "stock_specific",
                "scope_ticker": w.get("ticker"),
            })

    # India macro headlines — broader signal, smaller share.
    for n in context.get("india_headlines", [])[:8]:
        candidates.append({
            "id": n.get("id"),
            "headline": n.get("headline"),
            "source": n.get("source"),
            "scope": "macro",
            "scope_ticker": None,
        })

    # Global headlines (overnight) — most relevant for IT/Pharma/Auto exposure.
    for n in context.get("global_headlines", [])[:10]:
        candidates.append({
            "id": n.get("id"),
            "headline": n.get("headline"),
            "source": n.get("source"),
            "scope": "global",
            "scope_ticker": None,
            "country": n.get("country"),
        })

    return candidates[:90]  # generous cap for large portfolios


@router.post("/news-feed")
async def news_feed(req: NewsFeedRequest):
    """Annotated news stream — every relevant headline scored against the user's portfolio.

    Returns items with: impact_level, direction, affected_tickers (from user's universe),
    one-sentence reason, source citation. Items with no portfolio relevance are filtered out.
    """
    demo_mode = not req.positions and not req.watchlist_tickers
    if demo_mode:
        raw_positions = _DEMO_HOLDINGS
        watchlist = _DEMO_WATCHLIST
    else:
        raw_positions = [
            {"ticker": p.ticker, "quantity": p.quantity, "buy_price": p.buy_price}
            for p in req.positions
        ]
        watchlist = list(req.watchlist_tickers)

    cache_key = _news_feed_cache_key(raw_positions, watchlist)
    if not req.force_refresh and cache_key in _news_feed_cache:
        return _news_feed_cache[cache_key]

    if not ai_client.is_available():
        return with_disclaimer({
            "demo_mode": demo_mode,
            "items": [],
            "error": "AI client not configured.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    try:
        context = await asyncio.to_thread(
            grounding.build_morning_brief_context, raw_positions, watchlist
        )
    except Exception as e:
        logger.exception("news feed context build failed")
        return with_disclaimer({
            "demo_mode": demo_mode,
            "items": [],
            "error": f"Context build failed: {e}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    candidates = _collect_candidate_news(context)
    if not candidates:
        return with_disclaimer({
            "demo_mode": demo_mode,
            "items": [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "user_universe": context.get("user_universe", {}),
        })

    user_holdings = [h["ticker"] for h in context.get("holdings", [])]
    user_watchlist = [w["ticker"] for w in context.get("watchlist", [])]

    # Build a slim CONTEXT for batch annotation.
    annotation_ctx = {
        "user_holdings": user_holdings,
        "user_watchlist": user_watchlist,
        "sectors_today": [
            {"sector": s.get("sector"), "change_percent": s.get("change_percent")}
            for s in context.get("sectors", [])
        ],
        "candidate_news": candidates,
    }

    task = (
        "For EACH item in CONTEXT.candidate_news, decide whether it materially affects "
        "the user's portfolio (CONTEXT.user_holdings + CONTEXT.user_watchlist). For items "
        "that DO affect the portfolio, output an annotation. SKIP items that don't.\n\n"
        "STRICT RULES:\n"
        "1. affected_tickers MUST be a subset of CONTEXT.user_holdings + CONTEXT.user_watchlist. "
        "Never invent tickers.\n"
        "2. impact_level: 'high' if it directly hits a held name or a sector with >20% portfolio "
        "weight, 'medium' if mild sector/macro effect, 'low' if tangential. Skip if no impact.\n"
        "3. direction: 'positive' (tailwind for affected tickers), 'negative' (headwind), 'mixed' "
        "(some up some down).\n"
        "4. reason: ONE short sentence (<140 chars) explaining the transmission mechanism. "
        "Plain English. No jargon. Educational stance — never say buy/sell.\n"
        "5. category: 'stock_specific' (single ticker news), 'sector' (sector-wide), 'macro' "
        "(India macro), 'global' (overseas event with India impact).\n"
        "6. Order output by impact_level (high → medium → low). Cap at 30 items.\n"
        "7. For users with 20+ holdings, lean toward keeping items even at 'low' impact — "
        "the user wants breadth of coverage across their portfolio, not just headline events."
    )
    schema = """{
  "items": [
    {
      "news_id": str,                   // matches candidate_news[i].id
      "headline": str,                  // copy verbatim from candidate
      "source": str,                    // copy verbatim
      "category": "stock_specific" | "sector" | "macro" | "global",
      "impact_level": "high" | "medium" | "low",
      "direction": "positive" | "negative" | "mixed",
      "affected_tickers": [ str ],
      "reason": str
    }
  ],
  "data_gaps": [ str, ... ]
}"""

    try:
        data = await asyncio.wait_for(
            asyncio.to_thread(
                ai_client.generate_grounded_json, task, annotation_ctx, schema, 3500
            ),
            timeout=60,
        )
    except asyncio.TimeoutError:
        return with_disclaimer({
            "demo_mode": demo_mode,
            "items": [],
            "error": "Generation timed out.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    if not data:
        return with_disclaimer({
            "demo_mode": demo_mode,
            "items": [],
            "error": "AI returned unparseable response.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    universe = set(user_holdings) | set(user_watchlist)
    cleaned: list[dict] = []
    for it in (data.get("items") or [])[:30]:
        affected = [t for t in (it.get("affected_tickers") or []) if t in universe]
        if not affected:
            continue  # if no real impact on user, drop it
        cleaned.append({
            "news_id": it.get("news_id"),
            "headline": (it.get("headline") or "").strip()[:200],
            "source": it.get("source"),
            "category": it.get("category", "macro"),
            "impact_level": it.get("impact_level", "low"),
            "direction": it.get("direction", "mixed"),
            "affected_tickers": affected,
            "reason": (it.get("reason") or "").strip()[:200],
        })

    # Sort: high → medium → low (already requested in prompt but enforce server-side).
    impact_order = {"high": 0, "medium": 1, "low": 2}
    cleaned.sort(key=lambda x: impact_order.get(x["impact_level"], 3))

    payload = with_disclaimer({
        "demo_mode": demo_mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": cleaned,
        "user_universe": context.get("user_universe", {}),
        "data_gaps": data.get("data_gaps", []),
    })
    _news_feed_cache[cache_key] = payload
    return payload


# ---------------------------------------------------------------------------
# Market Summary — 60+ line narrative giving the user the day's full story
# in plain English. Sits to the LEFT of the news feed in the dashboard.
# ---------------------------------------------------------------------------
_market_summary_cache: TTLCache = TTLCache(maxsize=200, ttl=4 * 60 * 60)  # 4 hours


class MarketSummaryRequest(BaseModel):
    positions: list[PositionIn] = []
    watchlist_tickers: list[str] = []
    force_refresh: bool = False


def _summary_cache_key(positions: list[dict], watchlist: list[str]) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    h_key = ",".join(sorted({(p.get("ticker") or "").upper() for p in positions if p.get("ticker")}))
    w_key = ",".join(sorted({t.upper() for t in watchlist if t}))
    return f"summary|{today}|{h_key}|{w_key}"


@router.post("/market-summary")
async def market_summary(req: MarketSummaryRequest):
    """Long-form daily market narrative — 5-7 sections, ~60+ lines total.

    Newspaper-style explainer the user reads in 2 minutes to understand:
      - Overnight global moves and what they signal
      - Indian market open + sector breadth
      - Specific catalysts hitting the user's holdings
      - Sector-wide pressures or tailwinds
      - What to watch for the rest of the session and tomorrow
    """
    demo_mode = not req.positions and not req.watchlist_tickers
    if demo_mode:
        raw_positions = _DEMO_HOLDINGS
        watchlist = _DEMO_WATCHLIST
    else:
        raw_positions = [
            {"ticker": p.ticker, "quantity": p.quantity, "buy_price": p.buy_price}
            for p in req.positions
        ]
        watchlist = list(req.watchlist_tickers)

    cache_key = _summary_cache_key(raw_positions, watchlist)
    if not req.force_refresh and cache_key in _market_summary_cache:
        return _market_summary_cache[cache_key]

    if not ai_client.is_available():
        return with_disclaimer({
            "demo_mode": demo_mode,
            "sections": [],
            "error": "AI client not configured.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    try:
        context = await asyncio.to_thread(
            grounding.build_morning_brief_context, raw_positions, watchlist
        )
    except Exception as e:
        logger.exception("market summary context build failed")
        return with_disclaimer({
            "demo_mode": demo_mode,
            "sections": [],
            "error": f"Context build failed: {e}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    user_holdings = [h["ticker"] for h in context.get("holdings", [])]
    user_watchlist = [w["ticker"] for w in context.get("watchlist", [])]

    task = (
        "Write a comprehensive daily market summary for an Indian retail investor with "
        "the universe shown in CONTEXT. The output must read like a senior analyst's "
        "morning note — plain English, complete sentences, narrative flow.\n\n"
        "STRUCTURE — emit EXACTLY these 6 sections in this order:\n"
        "  1. 'overnight'         — what happened in US/EU/Asia overnight, ~3-4 sentences\n"
        "  2. 'india_open'        — Nifty/Sensex/sector breadth this morning, ~3-4 sentences\n"
        "  3. 'your_portfolio'    — direct catalysts hitting CONTEXT.holdings; name "
        "                           specific tickers and which news/sector moved them. "
        "                           ~5-7 sentences. THIS IS THE LONGEST SECTION.\n"
        "  4. 'sector_pulse'      — sector-wide forces relevant to the user's exposure; "
        "                           reference CONTEXT.user_universe.sector_exposure_pct. "
        "                           ~3-5 sentences.\n"
        "  5. 'watch_today'       — events likely to move things later today (RBI, "
        "                           earnings, results, data releases). ~3-4 sentences.\n"
        "  6. 'tomorrow_setup'    — overnight catalysts to watch (Fed, results, US data) "
        "                           and how they'd transmit to the user's holdings. "
        "                           ~3-4 sentences.\n\n"
        "STRICT RULES:\n"
        "1. NEVER recommend buy/sell/hold. Use stance language only ('tailwind', "
        "'headwind', 'watch', 'caution'). Educational, not advisory.\n"
        "2. Every analytical claim must reference a specific id from CONTEXT (e.g. "
        "global_news[2], INFY_news[0], sectors[i]). Cite inline as '(per global_news[2])'.\n"
        "3. Mention the user's specific tickers by name where relevant — this is "
        "personalized, not generic.\n"
        "4. Total output across all sections should be ~60 lines / ~500-700 words. "
        "Concise, readable, no fluff.\n"
        "5. If CONTEXT has thin data for a section, say so explicitly rather than padding."
    )
    schema = """{
  "sections": [
    {
      "id": "overnight" | "india_open" | "your_portfolio" | "sector_pulse" | "watch_today" | "tomorrow_setup",
      "title": str,                                  // human-friendly, e.g. "Overnight"
      "body": str,                                   // multi-sentence paragraph(s), inline source citations
      "stance": "tailwind" | "headwind" | "mixed" | "neutral",
      "key_tickers": [ str ]                         // tickers from CONTEXT mentioned in body
    }
  ],
  "headline": str,                                   // one-line takeaway for the whole day, <100 chars
  "confidence": "low" | "medium" | "high",
  "data_gaps": [ str, ... ]
}"""

    try:
        data = await asyncio.wait_for(
            asyncio.to_thread(
                ai_client.generate_grounded_json, task, context, schema, 2200
            ),
            timeout=60,
        )
    except asyncio.TimeoutError:
        return with_disclaimer({
            "demo_mode": demo_mode,
            "sections": [],
            "error": "Generation timed out.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    if not data:
        return with_disclaimer({
            "demo_mode": demo_mode,
            "sections": [],
            "error": "AI returned unparseable response.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    universe = set(user_holdings) | set(user_watchlist)
    sections = []
    for s in (data.get("sections") or [])[:6]:
        key_tickers = [t for t in (s.get("key_tickers") or []) if t in universe]
        sections.append({
            "id": s.get("id", "overnight"),
            "title": (s.get("title") or s.get("id") or "Section").strip()[:80],
            "body": (s.get("body") or "").strip(),
            "stance": s.get("stance", "neutral"),
            "key_tickers": key_tickers,
        })

    payload = with_disclaimer({
        "demo_mode": demo_mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "headline": (data.get("headline") or "").strip()[:200],
        "sections": sections,
        "user_universe": context.get("user_universe", {}),
        "confidence": data.get("confidence", "low"),
        "data_gaps": data.get("data_gaps", []),
    })
    _market_summary_cache[cache_key] = payload
    return payload
