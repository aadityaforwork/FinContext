"""
Advanced Analysis Router
========================
Endpoints for the advanced AI features (Simulator, DD Agent, Valuation Engine, Deep-Dive).

Every analytical LLM call is grounded in a real-data CONTEXT block produced by
app.services.grounding. The model is instructed to cite context paths and mark
unsupported fields as null — see services/ai_client.GROUNDING_CONTRACT.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncio
import json
import logging

from app.nse_universe import TICKER_TO_META
from app.services import ai_client, grounding

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class SimulateRequest(BaseModel):
    ticker: str
    scenario: str

class NarrativeRequest(BaseModel):
    text: str

class DDAgentRequest(BaseModel):
    ticker: str

class DeepDiveRequest(BaseModel):
    ticker: str


# ---------------------------------------------------------------------------
# 1. The "What-If" Scenario Simulator (grounded)
# ---------------------------------------------------------------------------
@router.post("/simulate")
async def simulate_scenario(req: SimulateRequest):
    """Estimate scenario impact on a stock using real financials + news as context."""
    ticker = req.ticker.upper()
    if not ai_client.is_available():
        raise HTTPException(status_code=500, detail="AI client not configured")

    context = await asyncio.to_thread(grounding.build_stock_context, ticker)
    if not context["meta"].get("name"):
        raise HTTPException(status_code=404, detail=f"Ticker {ticker} not found")

    task = (
        f"Given the scenario: \"{req.scenario}\", estimate its impact on "
        f"{context['meta']['name']} ({ticker}). Reason from the company's real financials, "
        f"recent news, and sector peer medians in CONTEXT. Quantify only what CONTEXT supports. "
        f"If margin/revenue impact cannot be derived from CONTEXT, return null."
    )
    schema = """{
  "impact_score_percent": float | null,     // estimated stock-price change
  "severity": "High" | "Medium" | "Low",
  "rationale": [ { "text": str, "source": str }, ... 3 items ],
  "revenue_estimate_change": str | null,    // e.g. "-3%"; null if unsupported
  "margin_impact_bps": int | null,
  "confidence": "low" | "medium" | "high",
  "data_gaps": [ str, ... ]
}"""
    data = await asyncio.to_thread(
        ai_client.generate_grounded_json, task, context, schema, 1024
    )
    if not data:
        raise HTTPException(status_code=502, detail="AI returned unparseable response")

    impact = data.get("impact_score_percent")
    direction = "Bullish" if (impact or 0) > 0 else "Bearish" if (impact or 0) < 0 else "Neutral"

    return {
        "ticker": ticker,
        "company": context["meta"]["name"],
        "scenario_analyzed": req.scenario,
        "impact": {
            "score_percent": impact,
            "severity": data.get("severity", "Medium"),
            "direction": direction,
        },
        "rationale": data.get("rationale", []),
        "adjusted_metrics": {
            "revenue_estimate_change": data.get("revenue_estimate_change"),
            "margin_impact_bps": data.get("margin_impact_bps"),
        },
        "confidence": data.get("confidence", "low"),
        "data_gaps": data.get("data_gaps", []),
        "context_snapshot_at": context.get("generated_at"),
    }


# ---------------------------------------------------------------------------
# 2. ELI5 Stock-Story (DD Agent) — grounded, streamed
# ---------------------------------------------------------------------------
async def dd_agent_generator(ticker: str):
    meta = TICKER_TO_META.get(ticker, {"name": ticker, "sector": "General"})

    for msg in [
        f"Fetching real financials for {ticker}...",
        "Benchmarking against sector peers...",
        "Reading latest news...",
        "Composing plain-English story...",
    ]:
        yield f"data: {json.dumps({'type': 'step', 'message': msg})}\n\n"
        await asyncio.sleep(0.3)

    if not ai_client.is_available():
        yield f"data: {json.dumps({'type':'step', 'message':'ERROR: AI client not configured.'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    try:
        context = await asyncio.to_thread(grounding.build_stock_context, ticker)
    except Exception as e:
        yield f"data: {json.dumps({'type':'step','message':f'Context build failed: {e}'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    task = (
        f"Explain the financial story of {meta['name']} ({ticker}) to a retail investor "
        f"(Explain Like I'm 5) using ONLY the facts in CONTEXT. Pros/cons must reference "
        f"specific ratios, peer medians, or news items from CONTEXT."
    )
    schema = """{
  "analogy": str,
  "health_score": int (1-100) | null,
  "pros": [ { "text": str, "source": str }, ... 2 items ],
  "cons": [ { "text": str, "source": str }, ... 2 items ],
  "bottom_line": str,
  "confidence": "low" | "medium" | "high",
  "data_gaps": [ str, ... ]
}"""
    try:
        data = await asyncio.wait_for(
            asyncio.to_thread(ai_client.generate_grounded_json, task, context, schema, 1024),
            timeout=45,
        )
    except asyncio.TimeoutError:
        yield f"data: {json.dumps({'type':'step','message':'Timed out waiting for model.'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    if not data:
        yield f"data: {json.dumps({'type':'error','message':'AI returned unparseable response'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    memo = {
        "type": "result",
        "company": meta["name"],
        "ticker": ticker,
        "analogy": data.get("analogy", ""),
        "health_score": data.get("health_score"),
        "pros": data.get("pros", []),
        "cons": data.get("cons", []),
        "bottom_line": data.get("bottom_line", ""),
        "confidence": data.get("confidence", "low"),
        "data_gaps": data.get("data_gaps", []),
        "context_snapshot_at": context.get("generated_at"),
    }
    yield f"data: {json.dumps(memo)}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/dd-agent")
async def deploy_dd_agent(req: DDAgentRequest):
    return StreamingResponse(
        dd_agent_generator(req.ticker.upper()),
        media_type="text/event-stream",
    )


# ---------------------------------------------------------------------------
# 3. Narrative-to-Numbers Valuation Engine
# ---------------------------------------------------------------------------
@router.post("/narrative-impact")
async def calculate_narrative_impact(req: NarrativeRequest):
    """The narrative itself IS the data source — no external context required."""
    if not ai_client.is_available():
        raise HTTPException(status_code=500, detail="AI client not configured")

    # Package the narrative as CONTEXT so the same grounding contract applies.
    context = {"narrative": req.text}
    task = (
        "Convert the narrative in CONTEXT into a structured financial-shock model. "
        "Every rationale must quote a phrase from CONTEXT.narrative as its source. "
        "If a numeric field is not supported by the narrative, return null."
    )
    schema = """{
  "sentiment": "Positive" | "Negative" | "Neutral",
  "severity_1_to_10": int | null,
  "estimated_price_impact_percent": float | null,
  "algorithmic_action": "Sell/Hedge" | "Accumulate" | "Hold",
  "revenue_adjustment": str | null,
  "ebitda_shock": str | null,
  "risk_factor": { "text": str, "source": "narrative" },
  "confidence": "low" | "medium" | "high",
  "data_gaps": [ str, ... ]
}"""
    data = await asyncio.to_thread(
        ai_client.generate_grounded_json, task, context, schema, 1024
    )
    if not data:
        raise HTTPException(status_code=502, detail="AI returned unparseable response")

    return {
        "source_text": req.text,
        "extraction": {
            "sentiment": data.get("sentiment", "Neutral"),
            "severity_1_to_10": data.get("severity_1_to_10"),
            "estimated_price_impact_percent": data.get("estimated_price_impact_percent"),
            "algorithmic_action": data.get("algorithmic_action", "Hold"),
        },
        "model_adjustments": {
            "revenue": data.get("revenue_adjustment"),
            "ebitda": data.get("ebitda_shock"),
        },
        "risk_factors": [data.get("risk_factor", {})],
        "confidence": data.get("confidence", "low"),
        "data_gaps": data.get("data_gaps", []),
    }


# ---------------------------------------------------------------------------
# 4. Deep-Dive — grounded + peer percentiles + verifier pass
# ---------------------------------------------------------------------------
async def deep_dive_generator(ticker: str):
    meta = TICKER_TO_META.get(ticker, {"name": ticker, "sector": "General"})

    for msg in [
        f"Deep-dive on {meta['name']} ({ticker})...",
        "Pulling real ratios from NSE data...",
        "Benchmarking against sector peers (percentile ranks)...",
        "Reading recent news...",
        "Drafting grounded analysis...",
        "Running fact-check verifier...",
    ]:
        yield f"data: {json.dumps({'type': 'step', 'message': msg})}\n\n"
        await asyncio.sleep(0.3)

    if not ai_client.is_available():
        yield f"data: {json.dumps({'type':'step','message':'ERROR: AI client not configured.'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    try:
        context = await asyncio.to_thread(grounding.build_stock_context, ticker)
    except Exception as e:
        yield f"data: {json.dumps({'type':'error','message':f'Context build failed: {e}'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    task = (
        f"Produce a premium equity research brief on {meta['name']} ({ticker}). "
        f"All financial numbers must come from CONTEXT.snapshot. All peer comparisons "
        f"must use CONTEXT.peer_benchmark.medians and CONTEXT.peer_benchmark.this_stock_percentile. "
        f"Upcoming catalysts must cite specific CONTEXT.news[i] items or be omitted. "
        f"Do not invent target prices — if CONTEXT does not provide analyst targets, "
        f"return null for target_low/target_high and add an entry to data_gaps."
    )
    schema = """{
  "moat_rating": "WIDE" | "NARROW" | "NONE",
  "moat_reason": { "text": str, "source": str },
  "financials": {
    "revenue_growth": str | null,   // from snapshot.revenue_growth_pct
    "profit_margin": str | null,    // from snapshot.profit_margin_pct
    "debt_to_equity": str | null,   // from snapshot.debt_to_equity
    "roe": str | null,              // from snapshot.roe_pct
    "vs_peers": {
      "pe_percentile": int | null,
      "roe_percentile": int | null,
      "margin_percentile": int | null
    }
  },
  "catalysts": [
    { "title": str, "timeline": str, "impact": "POSITIVE"|"NEGATIVE"|"NEUTRAL",
      "description": { "text": str, "source": str } }
  ],
  "verdict": {
    "action": "BUY" | "HOLD" | "SELL",
    "confidence": int (1-100),
    "target_low": float | null,
    "target_high": float | null,
    "thesis": { "text": str, "source": str }
  },
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

    # Verifier pass — strip any unsupported catalyst/rationale items
    verified = await asyncio.to_thread(ai_client.verify_claims, data, context, 1024)
    data = verified.get("verified", data)

    # Deterministic UI compat: compute *_score fields + alternatives from context.
    financials = data.get("financials") or {}
    scores = grounding.compute_financial_scores(context)
    for k, v in scores.items():
        if financials.get(k) is None:
            financials[k] = v
    alternatives = grounding.get_sector_alternatives(context, limit=2)

    result = {
        "type": "result",
        "company": meta["name"],
        "ticker": ticker,
        "sector": meta["sector"],
        "moat_rating": data.get("moat_rating", "NARROW"),
        "moat_reason": data.get("moat_reason", {}),
        "financials": financials,
        "catalysts": data.get("catalysts", []),
        "verdict": data.get("verdict", {}),
        "alternatives": alternatives,
        "confidence": data.get("confidence", "low"),
        "data_gaps": data.get("data_gaps", []),
        "removed_by_verifier": verified.get("removed", []),
        "context_snapshot_at": context.get("generated_at"),
    }
    yield f"data: {json.dumps(result)}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/deep-dive")
async def deep_dive_analysis(req: DeepDiveRequest):
    return StreamingResponse(
        deep_dive_generator(req.ticker.upper()),
        media_type="text/event-stream",
    )
