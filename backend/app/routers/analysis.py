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
from app.agents import base as agents_base
from app.agents.crews import narrative as narrative_crew
from app.core.compliance import with_disclaimer
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

    return with_disclaimer({
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
    })


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

    memo = with_disclaimer({
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
    })
    yield f"data: {json.dumps(memo)}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/dd-agent")
async def deploy_dd_agent(req: DDAgentRequest):
    return StreamingResponse(
        dd_agent_generator(req.ticker.upper()),
        media_type="text/event-stream",
    )


# ---------------------------------------------------------------------------
# 3. Narrative-to-Numbers — agent crew (Phase A)
# ---------------------------------------------------------------------------
def _shape_narrative_response(text: str, data: dict) -> dict:
    """Translate the crew/legacy output dict into the public response envelope."""
    return with_disclaimer({
        "source_text": text,
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
    })


async def _narrative_legacy_path(text: str) -> dict:
    """Pre-CrewAI single-call path. Kept as fallback when crewai is not installed
    or GROQ_API_KEY is missing — never delete; it is the safety net for prod."""
    if not ai_client.is_available():
        raise HTTPException(status_code=500, detail="AI client not configured")

    context = {"narrative": text}
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
    return data


@router.post("/narrative-impact")
async def calculate_narrative_impact(req: NarrativeRequest):
    """Run the 2-agent Narrative-to-Numbers crew. Falls back to the legacy single-call path
    if crewai is not installed or GROQ_API_KEY is missing."""
    if agents_base.is_available():
        try:
            data = await narrative_crew.run(req.text)
            if data:
                return _shape_narrative_response(req.text, data)
            logger.warning("narrative crew returned empty dict — falling back to legacy path")
        except Exception as e:
            logger.exception("narrative crew failed; falling back to legacy path: %s", e)

    data = await _narrative_legacy_path(req.text)
    return _shape_narrative_response(req.text, data)


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
        f"Produce an institutional-grade equity research brief on {meta['name']} ({ticker}). "
        f"This is the most important analysis a retail investor will read on this stock — "
        f"make it concrete, specific, and useful.\n\n"
        f"GROUNDING RULES (HARD):\n"
        f"• Every financial number must come from CONTEXT.snapshot — never invent.\n"
        f"• Every peer comparison must reference CONTEXT.peer_benchmark.medians and "
        f"the percentile in CONTEXT.peer_benchmark.this_stock_percentile.\n"
        f"• Bull/bear points must cite ratios from CONTEXT.snapshot OR signals from "
        f"CONTEXT.signals OR specific CONTEXT.news[i] items. No generic platitudes.\n"
        f"• Catalysts must cite specific CONTEXT.news[i] items or be omitted entirely.\n"
        f"• Do not invent target prices — if CONTEXT does not provide analyst targets, "
        f"return null and add to data_gaps.\n\n"
        f"BANNED PHRASES (do not use, ever):\n"
        f"• 'strong fundamentals' / 'solid fundamentals' / 'robust' (vague)\n"
        f"• 'well-positioned' / 'poised for growth' (filler)\n"
        f"• 'leading player' / 'market leader' unless CONTEXT proves it\n"
        f"• 'long-term value' / 'attractive valuation' without a specific multiple\n"
        f"• Action language: buy / sell / hold / accumulate / book profit\n\n"
        f"WRITING STYLE:\n"
        f"• Use specific numbers in every sentence. 'ROE 22% vs sector median 14%' "
        f"beats 'strong return on equity'.\n"
        f"• Bull/bear cases must be FALSIFIABLE — a thesis someone can disagree with "
        f"based on data, not vibes.\n"
        f"• valuation_read.stance is one of EXPENSIVE/FAIR/CHEAP — judge from P/E and "
        f"P/B percentile vs sector AND price position in 52w range.\n"
        f"• what_to_watch entries are concrete triggers: 'Q4 margin > 18%' or "
        f"'NIFTY IT crossing X' — not 'monitor earnings'.\n"
        f"• key_risks are stock-specific, not industry boilerplate.\n\n"
        f"COMPLIANCE (HARD): We are unregistered, not a SEBI RA. verdict.action must "
        f"be BULLISH/NEUTRAL/CAUTIOUS — assessment language, not advice."
    )
    schema = """{
  "one_liner": str,                 // 1-sentence what-this-company-does-and-why-it-matters (max 22 words)
  "moat_rating": "WIDE" | "NARROW" | "NONE",
  "moat_reason": { "text": str, "source": str },
  "financials": {
    "revenue_growth": str | null,
    "profit_margin": str | null,
    "debt_to_equity": str | null,
    "roe": str | null,
    "vs_peers": {
      "pe_percentile": int | null,
      "roe_percentile": int | null,
      "margin_percentile": int | null
    }
  },
  "valuation_read": {
    "stance": "EXPENSIVE" | "FAIR" | "CHEAP",
    "basis": { "text": str, "source": str }   // cite P/E vs peer median + 52w position
  },
  "bull_case": [                    // EXACTLY 3 items, each falsifiable + cited
    { "text": str, "source": str },
    { "text": str, "source": str },
    { "text": str, "source": str }
  ],
  "bear_case": [                    // EXACTLY 3 items, each falsifiable + cited
    { "text": str, "source": str },
    { "text": str, "source": str },
    { "text": str, "source": str }
  ],
  "key_risks": [                    // 2-3 STOCK-SPECIFIC risks (not generic)
    { "text": str, "source": str }
  ],
  "what_to_watch": [                // EXACTLY 3 concrete, observable triggers
    { "trigger": str, "why": str }
  ],
  "catalysts": [
    { "title": str, "timeline": str, "impact": "POSITIVE"|"NEGATIVE"|"NEUTRAL",
      "description": { "text": str, "source": str } }
  ],
  "verdict": {
    "action": "BULLISH" | "NEUTRAL" | "CAUTIOUS",
    "confidence": int,
    "target_low": float | null,
    "target_high": float | null,
    "thesis": { "text": str, "source": str }
  },
  "confidence": "low" | "medium" | "high",
  "data_gaps": [ str, ... ]
}"""

    try:
        data = await asyncio.wait_for(
            asyncio.to_thread(ai_client.generate_grounded_json, task, context, schema, 4000),
            timeout=90,
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

    # ------------------------------------------------------------------------
    # Confidence — computed deterministically from grounding signals, NOT
    # whatever number the LLM picks. The model's self-assessed confidence is
    # systematically optimistic (it doesn't know what's missing). This score
    # reflects the actual data quality behind the brief, so the UI confidence
    # bar tracks something real:
    #
    #   start at 100
    #   − for each missing core financial in snapshot   (incomplete fundamentals)
    #   − scaled penalty for small peer sample          (weak benchmark)
    #   − fixed penalty if no news context              (no catalyst evidence)
    #   − per-item penalty for admitted data_gaps       (LLM honesty signal)
    #   − per-item penalty for verifier removals        (claims that failed grounding)
    #   clamp 5..95 — never claim certainty, never claim nothing.
    # ------------------------------------------------------------------------
    snap = context.get("snapshot") or {}
    pb   = context.get("peer_benchmark") or {}
    news = context.get("news") or []
    core_fields = ("pe_ratio", "roe_pct", "profit_margin_pct",
                   "revenue_growth_pct", "debt_to_equity")
    missing_core = sum(1 for k in core_fields if snap.get(k) is None)

    score = 100
    score -= missing_core * 8                       # max −40
    n_peers = pb.get("n_peers_sampled", 0)
    if n_peers < 3:
        score -= 25
    elif n_peers < 6:
        score -= 12
    if not news:
        score -= 10
    gaps_penalty = min(20, len(data.get("data_gaps") or []) * 4)
    score -= gaps_penalty
    rem_penalty = min(20, len(verified.get("removed") or []) * 5)
    score -= rem_penalty
    score = max(5, min(95, score))

    # Map int → qualitative band consistently across the response.
    conf_label = "high" if score >= 70 else "medium" if score >= 40 else "low"

    verdict = data.get("verdict") or {}
    verdict["confidence"] = score
    verdict["confidence_label"] = conf_label
    verdict["confidence_basis"] = {
        "missing_core_financials": missing_core,
        "peers_sampled": n_peers,
        "news_count": len(news),
        "data_gaps": len(data.get("data_gaps") or []),
        "claims_removed": len(verified.get("removed") or []),
    }

    result = with_disclaimer({
        "type": "result",
        "company": meta["name"],
        "ticker": ticker,
        "sector": meta["sector"],
        "one_liner": data.get("one_liner", ""),
        "moat_rating": data.get("moat_rating", "NARROW"),
        "moat_reason": data.get("moat_reason", {}),
        "financials": financials,
        "valuation_read": data.get("valuation_read", {}),
        "bull_case": data.get("bull_case", []),
        "bear_case": data.get("bear_case", []),
        "key_risks": data.get("key_risks", []),
        "what_to_watch": data.get("what_to_watch", []),
        "catalysts": data.get("catalysts", []),
        "verdict": verdict,
        "alternatives": alternatives,
        "confidence": conf_label,
        "data_gaps": data.get("data_gaps", []),
        "removed_by_verifier": verified.get("removed", []),
        "context_snapshot_at": context.get("generated_at"),
        "snapshot": {
            "current_price": (context.get("snapshot") or {}).get("current_price"),
            "change_percent": (context.get("snapshot") or {}).get("change_percent"),
            "52w_high": (context.get("snapshot") or {}).get("52w_high"),
            "52w_low": (context.get("snapshot") or {}).get("52w_low"),
            "pe_ratio": (context.get("snapshot") or {}).get("pe_ratio"),
            "market_cap": (context.get("snapshot") or {}).get("market_cap"),
        },
    })
    yield f"data: {json.dumps(result)}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/deep-dive")
async def deep_dive_analysis(req: DeepDiveRequest):
    return StreamingResponse(
        deep_dive_generator(req.ticker.upper()),
        media_type="text/event-stream",
    )
