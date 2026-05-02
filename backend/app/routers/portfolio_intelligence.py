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
        "return sector or factor suggestions."
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
      "signal": "BUY" | "HOLD" | "REDUCE",
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
