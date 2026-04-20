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

from app.services import ai_client, grounding

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/intelligence", tags=["portfolio-intelligence"])


class PositionIn(BaseModel):
    ticker: str
    quantity: float
    buy_price: float


class IntelRequest(BaseModel):
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

    result = {
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
    }
    yield f"data: {json.dumps(result)}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/portfolio")
async def portfolio_intelligence(req: IntelRequest):
    if not req.positions:
        return {"error": "No holdings provided."}
    raw = [{"ticker": p.ticker, "quantity": p.quantity, "buy_price": p.buy_price} for p in req.positions]
    return StreamingResponse(_intelligence_generator(raw), media_type="text/event-stream")
