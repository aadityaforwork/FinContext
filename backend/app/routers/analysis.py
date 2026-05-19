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
from app.services import ai_client, grounding, technicals

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
    # "long_term" (default) → existing moat / bull / bear / valuation brief.
    # "swing"               → 1-3 month horizon: setup, momentum, key levels,
    #                         near-term catalysts. Different prompt + schema.
    horizon: str = "long_term"


class PreTradeCheckRequest(BaseModel):
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


# ---------------------------------------------------------------------------
# 5. Swing-trade brief — 1-3 month horizon
# ---------------------------------------------------------------------------
# Different lens entirely from the long-term deep-dive:
#   - Moat / DCF / years-of-growth are noise at this horizon.
#   - What matters: current technical phase, momentum strength, where the key
#     support/resistance levels sit, what catalyst could move it in 4-12 weeks.
#
# Compliance note: this is the closest we get to "trading content" and the
# fence is strict — we communicate STANCE and KEY LEVELS but never entry
# prices, stops, or position sizes. Education, not advice. The disclaimer
# wrapper enforces this at the response envelope.
# ---------------------------------------------------------------------------
def _derive_key_levels(snap: dict, tech: dict | None) -> dict | None:
    """Compute concrete support/resistance levels from snapshot + technicals.
    Returns None if we don't have enough data. Deterministic — no LLM.

    Levels:
      immediate_support:    20-day low (short-term floor from recent action)
      key_support:          52-week low (worst-case floor)
      immediate_resistance: 20-day high
      key_resistance:       52-week high
    """
    if not snap or not snap.get("current_price"):
        return None
    cp = snap["current_price"]
    hi_52 = snap.get("52w_high")
    lo_52 = snap.get("52w_low")
    # Reconstruct 20d high/low from technicals if available (pct distance from close).
    imm_hi = imm_lo = None
    if tech:
        pfh = tech.get("pct_from_20d_high")  # negative number if below high
        pfl = tech.get("pct_from_20d_low")   # positive number if above low
        if pfh is not None:
            imm_hi = round(cp / (1 + pfh / 100), 2)
        if pfl is not None:
            imm_lo = round(cp / (1 + pfl / 100), 2)
    return {
        "current_price": cp,
        "immediate_support": imm_lo,
        "immediate_resistance": imm_hi,
        "key_support": lo_52,
        "key_resistance": hi_52,
        # Distance summary the UI uses for the level chart:
        "distance_to_imm_support_pct":    round((cp - imm_lo) / cp * 100, 2) if imm_lo else None,
        "distance_to_imm_resistance_pct": round((imm_hi - cp) / cp * 100, 2) if imm_hi else None,
        "distance_to_key_support_pct":    round((cp - lo_52) / cp * 100, 2) if lo_52 else None,
        "distance_to_key_resistance_pct": round((hi_52 - cp) / cp * 100, 2) if hi_52 else None,
    }


async def swing_dive_generator(ticker: str):
    meta = TICKER_TO_META.get(ticker, {"name": ticker, "sector": "General"})

    for msg in [
        f"Swing read on {meta['name']} ({ticker})...",
        "Pulling intraday + 3-month price history...",
        "Computing RSI, momentum, volume profile...",
        "Mapping support and resistance levels...",
        "Cross-checking news catalysts for next 4-12 weeks...",
        "Drafting setup brief...",
    ]:
        yield f"data: {json.dumps({'type': 'step', 'message': msg})}\n\n"
        await asyncio.sleep(0.25)

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

    # Augment context with technicals — same payload the per-holding card uses.
    tech = await asyncio.to_thread(technicals.compute_signals, ticker)
    if tech:
        context["technicals"] = tech
    snap = context.get("snapshot") or {}
    levels = _derive_key_levels(snap, tech)
    if levels:
        context["key_levels"] = levels

    task = (
        f"Produce a SWING-TRADE BRIEF for {meta['name']} ({ticker}) on a 1 to 3 "
        f"month horizon. Different lens than a long-term investment brief — "
        f"moat / DCF / 5-year growth do NOT matter here. What matters is the "
        f"current technical phase, momentum strength, key levels, and whether "
        f"a catalyst is likely in the next 4-12 weeks.\n\n"
        f"GROUNDING RULES (HARD):\n"
        f"• Every momentum claim must cite CONTEXT.technicals (RSI, vol, SMA, "
        f"momentum_5d_pct / 20d_pct).\n"
        f"• Every level must reference CONTEXT.key_levels or CONTEXT.snapshot.\n"
        f"• Catalyst items must cite specific CONTEXT.news[i] items or be omitted.\n"
        f"• If a field cannot be derived from CONTEXT, return null + add to data_gaps.\n\n"
        f"BANNED:\n"
        f"• Entry prices, stop losses, position sizing, target prices — these "
        f"are advice-tier. We communicate STANCE and KEY LEVELS only.\n"
        f"• Action verbs: buy / sell / enter / exit / book.\n"
        f"• Vague filler: 'strong momentum', 'looks good', 'breakout candidate' "
        f"without specific numbers.\n\n"
        f"STYLE:\n"
        f"• Every sentence has a specific number from CONTEXT.\n"
        f"• Bull/bear cases are SHORT-TERM (4-12 weeks), not long-term.\n"
        f"• what_to_watch are observable triggers like 'RSI cross above 60' or "
        f"'volume above 1.5x avg on a green day' — not vague monitoring.\n"
        f"• one_liner frames the current SETUP, e.g. 'Tight consolidation above "
        f"the 50-DMA, awaiting a volume confirmation.'\n\n"
        f"COMPLIANCE (HARD): We are unregistered (not a SEBI RA). stance must "
        f"be BULLISH/NEUTRAL/CAUTIOUS — assessment, not trade advice."
    )
    schema = """{
  "one_liner": str,                       // 1-sentence setup framing (max 22 words)
  "setup": {
    "stance": "BULLISH" | "NEUTRAL" | "CAUTIOUS",
    "phase": "TRENDING_UP" | "CONSOLIDATING" | "TRENDING_DOWN" | "REVERSAL_UP" | "REVERSAL_DOWN",
    "phase_basis": { "text": str, "source": str }
  },
  "momentum": {
    "rsi_read":    str,                   // "RSI 62 — strong, room before overbought"
    "trend_read":  str,                   // "Above SMA50, 5d +2.4%, 20d +9.1%"
    "volume_read": str,                   // "Volume 1.8× 20d avg — accumulation"
    "score_0_100": int                    // composite momentum score
  },
  "bull_case": [                          // EXACTLY 3, SHORT-TERM only
    { "text": str, "source": str },
    { "text": str, "source": str },
    { "text": str, "source": str }
  ],
  "bear_case": [                          // EXACTLY 3, SHORT-TERM only
    { "text": str, "source": str },
    { "text": str, "source": str },
    { "text": str, "source": str }
  ],
  "what_to_watch": [                      // EXACTLY 3 observable triggers
    { "trigger": str, "why": str }
  ],
  "key_risks": [                          // 2-3 short-term, stock-specific risks
    { "text": str, "source": str }
  ],
  "horizon_note": str,                    // 1 line: when to re-evaluate (e.g. "Re-check at earnings or break of 1820 support")
  "confidence": "low" | "medium" | "high",
  "data_gaps": [ str, ... ]
}"""

    try:
        data = await asyncio.wait_for(
            asyncio.to_thread(ai_client.generate_grounded_json, task, context, schema, 3000),
            timeout=80,
        )
    except asyncio.TimeoutError:
        yield f"data: {json.dumps({'type':'error','message':'Timed out.'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    if not data:
        yield f"data: {json.dumps({'type':'error','message':'AI returned unparseable response.'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    # Deterministic confidence — same rubric as long-term, plus a hard penalty
    # if we don't even have technicals (the whole point of swing).
    score = 100
    if not tech:
        score -= 35
    if not (context.get("news") or []):
        score -= 10
    gaps_penalty = min(20, len(data.get("data_gaps") or []) * 4)
    score -= gaps_penalty
    if not levels:
        score -= 15
    score = max(5, min(95, score))
    conf_label = "high" if score >= 70 else "medium" if score >= 40 else "low"

    setup = data.get("setup") or {}
    setup["confidence"] = score
    setup["confidence_label"] = conf_label
    setup["confidence_basis"] = {
        "has_technicals": bool(tech),
        "has_key_levels": bool(levels),
        "news_count": len(context.get("news") or []),
        "data_gaps": len(data.get("data_gaps") or []),
    }

    result = with_disclaimer({
        "type": "result",
        "horizon": "swing",
        "company": meta["name"],
        "ticker": ticker,
        "sector": meta["sector"],
        "one_liner": data.get("one_liner", ""),
        "setup": setup,
        "momentum": data.get("momentum", {}),
        "bull_case": data.get("bull_case", []),
        "bear_case": data.get("bear_case", []),
        "what_to_watch": data.get("what_to_watch", []),
        "key_risks": data.get("key_risks", []),
        "horizon_note": data.get("horizon_note", ""),
        "key_levels": levels,
        "technicals": tech,
        "confidence": conf_label,
        "data_gaps": data.get("data_gaps", []),
        "context_snapshot_at": context.get("generated_at"),
        "snapshot": {
            "current_price":   snap.get("current_price"),
            "change_percent":  snap.get("change_percent"),
            "52w_high":        snap.get("52w_high"),
            "52w_low":         snap.get("52w_low"),
            "market_cap":      snap.get("market_cap"),
        },
    })
    yield f"data: {json.dumps(result)}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/deep-dive")
async def deep_dive_analysis(req: DeepDiveRequest):
    horizon = (req.horizon or "long_term").lower()
    gen = swing_dive_generator if horizon == "swing" else deep_dive_generator
    return StreamingResponse(
        gen(req.ticker.upper()),
        media_type="text/event-stream",
    )


# ---------------------------------------------------------------------------
# 6. Pre-Trade Check — deterministic scorecard, NO LLM, sub-2-second
# ---------------------------------------------------------------------------
# Product positioning: "the thing you check before you hit buy on Zerodha."
#
# Compliance shape: this is NOT a recommendation. It is a checklist of factors
# a careful investor would inspect. Status labels are PASS / CAUTION / FAIL on
# each factor in isolation; the top-line is just a count, never a verdict.
# Every line carries a `why` so the user learns the framework, not just the
# verdict — education, not advice.
#
# Speed: pulls from already-cached grounding context + technicals. No LLM call,
# no fresh peer fetch. If a check's data is missing (e.g. no technicals), the
# check is omitted from the scorecard rather than guessing.
# ---------------------------------------------------------------------------
def _check(check_id: str, label: str, status: str, value: str, why: str) -> dict:
    return {"id": check_id, "label": label, "status": status, "value": value, "why": why}


def _compute_pretrade_checks(context: dict, tech: dict | None) -> list[dict]:
    """Run the 6 deterministic checks. Each returns PASS / CAUTION / FAIL or
    is skipped entirely if its input data isn't available. The order matters —
    it's the order rendered in the UI, structured from most-immediate (price
    extension) to most-contextual (trend / 52w position)."""
    checks: list[dict] = []
    snap = context.get("snapshot") or {}
    pb   = context.get("peer_benchmark") or {}
    medians = pb.get("medians") or {}

    # 1. RSI — is the stock overbought / oversold right now?
    if tech and tech.get("rsi14") is not None:
        rsi = tech["rsi14"]
        if rsi >= 80:
            status = "FAIL"; why = "RSI ≥ 80 — strongly overbought; recent buyers have priced in a lot."
        elif rsi >= 70:
            status = "CAUTION"; why = "RSI ≥ 70 — overbought; pullback risk elevated short-term."
        elif rsi <= 20:
            status = "CAUTION"; why = "RSI ≤ 20 — deeply oversold; may bounce but could also indicate distress."
        elif rsi <= 30:
            status = "CAUTION"; why = "RSI ≤ 30 — oversold; technical bounce possible but check the why."
        else:
            status = "PASS"; why = "RSI in healthy 30–70 range — neither extended nor washed out."
        checks.append(_check("rsi", "Price not extended", status, f"RSI {round(rsi)}", why))

    # 2. Distance from 20-DMA — is the entry pressing a short-term mean?
    if tech and tech.get("pct_from_sma20") is not None:
        dist = tech["pct_from_sma20"]
        abs_d = abs(dist)
        sign = "+" if dist >= 0 else "−"
        if abs_d <= 5:
            status = "PASS"; why = "Within 5% of 20-day moving average — not stretched from short-term mean."
        elif abs_d <= 10:
            status = "CAUTION"; why = f"{round(abs_d)}% from 20-DMA — somewhat extended; mean-reversion risk."
        else:
            status = "FAIL"; why = f"{round(abs_d)}% from 20-DMA — heavily extended; high reversion risk."
        checks.append(_check("dist_sma20", "Not stretched from mean", status, f"{sign}{round(abs_d, 1)}% from SMA20", why))

    # 3. Volume vs 20-day average — is today abnormal?
    if tech and tech.get("vol_vs_avg20") is not None:
        vx = tech["vol_vs_avg20"]
        if vx >= 3.0:
            status = "FAIL"; why = "Volume ≥ 3× avg — climactic; either capitulation or blowoff. Wait for the dust."
        elif vx >= 2.0:
            status = "CAUTION"; why = "Volume ≥ 2× avg — surge; often marks a short-term inflection."
        elif vx <= 0.3:
            status = "CAUTION"; why = "Volume ≤ 0.3× avg — very thin; price moves are unreliable signals."
        else:
            status = "PASS"; why = "Volume within normal range — price action is on representative flow."
        checks.append(_check("volume", "Volume is normal", status, f"{vx}× 20d avg", why))

    # 4. Valuation vs sector peer median (P/E)
    pe = snap.get("pe_ratio")
    med_pe = medians.get("pe_ratio")
    if pe is not None and med_pe and med_pe > 0:
        ratio = pe / med_pe
        diff_pct = round((ratio - 1) * 100)
        if ratio > 1.6:
            status = "FAIL"; why = f"P/E {round(pe)} is {diff_pct}% above sector median {round(med_pe)} — pricing in big growth."
        elif ratio > 1.3:
            status = "CAUTION"; why = f"P/E {round(pe)} is {diff_pct}% above sector median {round(med_pe)} — modest premium."
        elif ratio < 0.7:
            status = "PASS"; why = f"P/E {round(pe)} is {abs(diff_pct)}% below sector median {round(med_pe)} — relative value."
        else:
            status = "PASS"; why = f"P/E {round(pe)} sits near sector median {round(med_pe)} — fairly valued vs peers."
        checks.append(_check("valuation", "Valuation vs sector", status, f"P/E {round(pe)} vs med {round(med_pe)}", why))

    # 5. 52-week position
    cp = snap.get("current_price")
    hi = snap.get("52w_high")
    lo = snap.get("52w_low")
    if cp and hi and lo and hi > lo:
        band = round((cp - lo) / (hi - lo) * 100)
        if band >= 95:
            status = "CAUTION"; why = "≥ 95% of 52-week range — near the top; thinner air, less margin of error."
        elif band <= 5:
            status = "CAUTION"; why = "≤ 5% of 52-week range — near the floor; could be value or could be falling."
        elif band >= 80:
            status = "CAUTION"; why = f"{band}% of 52-week range — upper end; price has run."
        else:
            status = "PASS"; why = f"{band}% of 52-week range — mid-range, room either way."
        checks.append(_check("range_52w", "52-week range position", status, f"{band}% of range", why))

    # 6. Trend state (relative to SMA50)
    if tech and tech.get("sma_state"):
        state = tech["sma_state"]
        mom = (tech.get("momentum_state") or "").replace("_", " ")
        if state == "above_sma50":
            status = "PASS"; why = "Trading above 50-day moving average — primary trend is up."
            val = "Above SMA50"
        else:
            status = "CAUTION"; why = "Trading below 50-day moving average — primary trend is down; buying a downtrend takes conviction."
            val = "Below SMA50"
        if mom:
            val += f" · {mom}"
        checks.append(_check("trend", "Primary trend", status, val, why))

    return checks


@router.post("/pre-trade-check")
async def pre_trade_check(req: PreTradeCheckRequest):
    """Fast, deterministic checklist. No LLM. Sub-2-second.

    Designed to be the muscle-memory check a user runs before clicking buy:
    six grounded factors, each with a PASS/CAUTION/FAIL and a 1-line why.
    Top-line is a count — never a verdict. We do not say "buy" or "don't buy".
    """
    ticker = req.ticker.upper()
    meta = TICKER_TO_META.get(ticker)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Ticker {ticker} not found in NSE universe")

    # Both calls hit caches first — sub-second when warm. Run them concurrently.
    context_task = asyncio.to_thread(grounding.build_stock_context, ticker, False, 0)
    tech_task    = asyncio.to_thread(technicals.compute_signals, ticker)
    context, tech = await asyncio.gather(context_task, tech_task)

    checks = _compute_pretrade_checks(context, tech)

    summary = {
        "passes":   sum(1 for c in checks if c["status"] == "PASS"),
        "cautions": sum(1 for c in checks if c["status"] == "CAUTION"),
        "fails":    sum(1 for c in checks if c["status"] == "FAIL"),
        "total":    len(checks),
    }

    snap = context.get("snapshot") or {}
    return with_disclaimer({
        "ticker": ticker,
        "company": meta.get("name", ticker),
        "sector":  meta.get("sector", ""),
        "current_price":  snap.get("current_price"),
        "change_percent": snap.get("change_percent"),
        "checks":   checks,
        "summary":  summary,
        "generated_at": context.get("generated_at"),
    })
