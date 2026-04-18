"""
Advanced Analysis Router
========================
Endpoints for the 3 advanced AI features (Simulator, DD Agent, Valuation Engine).
Integrates real Google Gemini API calls.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncio
import json
import logging
import random
import re

from app.nse_universe import TICKER_TO_META
from app.services import ai_client

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


# ---------------------------------------------------------------------------
# Helpers to parse JSON from generic text
# ---------------------------------------------------------------------------
def _extract_json_from_md(text: str) -> dict:
    if not text:
        logger.error("LLM returned empty text")
        return {}
    candidates = []
    if "```json" in text:
        candidates.append(text.split("```json", 1)[1].split("```", 1)[0].strip())
    if "```" in text:
        candidates.append(text.split("```", 1)[1].split("```", 1)[0].strip())
    candidates.append(text.strip())
    # Fallback: first { ... last } block
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        candidates.append(m.group(0))
    for c in candidates:
        try:
            return json.loads(c)
        except Exception:
            continue
    logger.error("Failed to parse JSON from LLM output. First 500 chars: %s", text[:500])
    return {}


# ---------------------------------------------------------------------------
# 1. The "What-If" Scenario Simulator
# ---------------------------------------------------------------------------
@router.post("/simulate")
async def simulate_scenario(req: SimulateRequest):
    """
    Analyzes how a hypothetical scenario impacts a specific stock.
    Returns structured impact data and rationale from Gemini.
    """
    ticker = req.ticker.upper()
    meta = TICKER_TO_META.get(ticker, {"name": ticker, "sector": "General"})
    
    if not ai_client.is_available():
        raise HTTPException(status_code=500, detail="Gemini API Key missing")

    prompt = f"""
You are a highly analytical quantitative modeler.
Analyze the impact of the following hypothetical scenario on this specific company:
Company: {meta["name"]} ({ticker})
Sector: {meta["sector"]}
Scenario: "{req.scenario}"

Respond ONLY with a valid JSON block containing exactly these keys:
- "impact_score_percent": a float representing estimated stock price change (e.g., -5.5 or 4.2).
- "severity": string ("High", "Medium", or "Low").
- "rationale": array of 3 descriptive strings explaining the causal links from the macro shock to company-specific margins/revenue.
- "revenue_estimate_change": string (e.g., "+3%", "-5%").
- "margin_impact_bps": integer (e.g., -150, 50).
"""
    try:
        text = await asyncio.to_thread(ai_client.generate_json, prompt, 1024)
        data = _extract_json_from_md(text)

        impact_score = float(data.get("impact_score_percent", 0.0))
        is_positive = impact_score > 0
        severity = data.get("severity", "Medium")
        
        return {
            "ticker": ticker,
            "company": meta["name"],
            "scenario_analyzed": req.scenario,
            "impact": {
                "score_percent": impact_score,
                "severity": severity,
                "direction": "Bullish" if is_positive else "Bearish" if impact_score < 0 else "Neutral"
            },
            "rationale": data.get("rationale", ["No rationale provided."]),
            "adjusted_metrics": {
                "revenue_estimate_change": data.get("revenue_estimate_change", "0%"),
                "margin_impact_bps": data.get("margin_impact_bps", 0),
                "risk_rating": "Elevated" if severity == "High" else "Standard"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# 2. Autonomous Due Diligence (DD) Agent - STREAMING
# ---------------------------------------------------------------------------
async def dd_agent_generator(ticker: str):
    """
    Yields Server-Sent Events (SSE) streaming reasoning steps,
    then the final investment memo from Gemini.
    """
    meta = TICKER_TO_META.get(ticker, {"name": ticker, "sector": "General"})
    
    steps = [
        {"type": "step", "message": f"Initializing AI Stock Story Engine for {ticker}..." },
        {"type": "step", "message": "Simplifying financial statements..." },
        {"type": "step", "message": "Translating sector jargon into everyday analogies..." },
        {"type": "step", "message": "Calculating simple overall health score..." },
        {"type": "step", "message": "Drafting the ELI5 summary..." },
    ]

    for step in steps:
        await asyncio.sleep(0.5)
        yield f"data: {json.dumps(step)}\n\n"
        
    if not ai_client.is_available():
        yield f"data: {json.dumps({'type':'step', 'message':'ERROR: No Gemini API Key found.'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    prompt = f"""
You are a Friendly Financial Educator. Your goal is to explain the complex financial state of the Indian company {meta['name']} ({ticker}) operating in {meta['sector']} to a completely normal retail investor (Explain Like I'm 5).

Respond ONLY with a valid JSON block containing exactly these keys:
- "analogy": string, a creative, easy-to-understand analogy explaining the company's current financial situation (e.g., comparing it to a lemonade stand, a sports team, etc.).
- "health_score": integer between 1 and 100 representing overall financial health and potential.
- "pros": array of 2 very simple, jargon-free positive points. 
- "cons": array of 2 very simple, jargon-free negative points.
- "bottom_line": string, a 1-sentence simple summary of whether it's looking good or bad right now.
"""
    try:
        # Offload API call to a thread so we don't block the async generator
        text = await asyncio.wait_for(
            asyncio.to_thread(ai_client.generate_json, prompt, 1024),
            timeout=45
        )
        data = _extract_json_from_md(text)

        memo = {
            "type": "result",
            "company": meta["name"],
            "ticker": ticker,
            "analogy": data.get("analogy", ""),
            "health_score": data.get("health_score", 50),
            "pros": data.get("pros", []),
            "cons": data.get("cons", []),
            "bottom_line": data.get("bottom_line", "")
        }
        yield f"data: {json.dumps(memo)}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type':'step', 'message':f'Generation failed: {str(e)}'})}\n\n"

    yield "data: [DONE]\n\n"


@router.post("/dd-agent")
async def deploy_dd_agent(req: DDAgentRequest):
    """
    Deploys the DD agent. Returns a StreamingResponse (SSE).
    """
    ticker = req.ticker.upper()
    return StreamingResponse(
        dd_agent_generator(ticker),
        media_type="text/event-stream"
    )


# ---------------------------------------------------------------------------
# 3. Narrative-to-Numbers Valuation Engine
# ---------------------------------------------------------------------------
@router.post("/narrative-impact")
async def calculate_narrative_impact(req: NarrativeRequest):
    """
    Takes raw news text / tweets and extracts a structured quantitative model 
    using Gemini.
    """
    if not ai_client.is_available():
        raise HTTPException(status_code=500, detail="Gemini API Key missing")

    prompt = f"""
You are a quantitative modeling system. Translate the following unstructured news narrative into a structured financial shock model.

Input Narrative:
"{req.text}"

Respond ONLY with a valid JSON block containing exactly these keys:
- "sentiment": string ("Positive", "Negative", or "Neutral").
- "severity_1_to_10": integer between 1 and 10.
- "estimated_price_impact_percent": float (e.g. -4.5 or 2.1).
- "algorithmic_action": string ("Sell/Hedge", "Accumulate", or "Hold").
- "revenue_adjustment": string representing the relative % revenue adjustment to consensus (e.g. "-10%" or "+5%").
- "ebitda_shock": string representing the relative % ebitda adjustment to consensus (e.g. "-15%" or "+8%").
- "risk_factor": string, a single sentence noting a key risk or caveat to this model.
"""
    
    try:
        text = await asyncio.to_thread(ai_client.generate_json, prompt, 1024)
        data = _extract_json_from_md(text)

        return {
            "source_text": req.text,
            "extraction": {
                "sentiment": data.get("sentiment", "Neutral"),
                "severity_1_to_10": data.get("severity_1_to_10", 1),
                "estimated_price_impact_percent": data.get("estimated_price_impact_percent", 0.0),
                "algorithmic_action": data.get("algorithmic_action", "Hold")
            },
            "model_adjustments": {
                "revenue": data.get("revenue_adjustment", "0%"),
                "ebitda": data.get("ebitda_shock", "0%")
            },
            "risk_factors": [
                data.get("risk_factor", "Market may have partially priced this in already.")
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# 4. Deep-Dive Analysis — Premium Comprehensive Analysis (SSE)
# ---------------------------------------------------------------------------
class DeepDiveRequest(BaseModel):
    ticker: str

async def deep_dive_generator(ticker: str):
    """Stream a comprehensive deep-dive analysis as SSE."""
    meta = TICKER_TO_META.get(ticker, {"name": ticker, "sector": "General"})

    steps = [
        {"type": "step", "message": f"Initiating deep-dive on {meta['name']} ({ticker})..."},
        {"type": "step", "message": "Analyzing competitive moat and market position..."},
        {"type": "step", "message": "Evaluating financial health metrics..."},
        {"type": "step", "message": "Scanning for upcoming catalysts..."},
        {"type": "step", "message": "Identifying peer alternatives..."},
        {"type": "step", "message": "Generating smart verdict..."},
    ]

    for step in steps:
        await asyncio.sleep(0.4)
        yield f"data: {json.dumps(step)}\n\n"

    if not ai_client.is_available():
        yield f"data: {json.dumps({'type': 'step', 'message': 'ERROR: Gemini API key missing.'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    prompt = f"""You are a world-class equity research analyst covering Indian markets. Produce a premium deep-dive analysis for:

Company: {meta['name']} ({ticker})
Sector: {meta['sector']}

Respond ONLY with a valid JSON object with these exact keys:

- "moat_rating": string, one of "WIDE", "NARROW", or "NONE"
- "moat_reason": string, 2-sentence explanation of the competitive advantage (or lack thereof)

- "financials": object with keys:
  - "revenue_growth": string (e.g. "+18% YoY")
  - "profit_margin": string (e.g. "12.5%")
  - "debt_to_equity": string (e.g. "0.3x")
  - "roe": string (e.g. "22%")
  - "revenue_growth_score": integer 1-100
  - "margin_score": integer 1-100
  - "debt_score": integer 1-100
  - "roe_score": integer 1-100

- "catalysts": array of 3 objects, each with:
  - "title": string (short event name)
  - "timeline": string (e.g. "Q1 2026", "Next 3 months")
  - "impact": "POSITIVE" or "NEGATIVE" or "NEUTRAL"
  - "description": string (1 sentence)

- "verdict": object with:
  - "action": "BUY" or "HOLD" or "SELL"
  - "confidence": integer 1-100
  - "target_low": float (conservative target price in INR)
  - "target_high": float (optimistic target price in INR)
  - "thesis": string (2-sentence investment thesis)

- "alternatives": array of 2 objects, each with:
  - "ticker": string (NSE symbol)
  - "name": string
  - "why": string (1-sentence reason why it's a better or complementary pick)
  - "edge": string (one key advantage over {ticker})
"""

    try:
        text = await asyncio.to_thread(ai_client.generate_json, prompt, 2048)
        data = _extract_json_from_md(text)
        if not data:
            yield f"data: {json.dumps({'type': 'error', 'message': 'AI returned unparseable response. Check backend logs.'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        result = {
            "type": "result",
            "company": meta["name"],
            "ticker": ticker,
            "sector": meta["sector"],
            "moat_rating": data.get("moat_rating", "NARROW"),
            "moat_reason": data.get("moat_reason", ""),
            "financials": data.get("financials", {}),
            "catalysts": data.get("catalysts", []),
            "verdict": data.get("verdict", {}),
            "alternatives": data.get("alternatives", []),
        }
        yield f"data: {json.dumps(result)}\n\n"
    except Exception as e:
        logger.error("Deep-dive failed", exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'message': f'Deep-dive failed: {str(e)[:300]}'})}\n\n"

    yield "data: [DONE]\n\n"


@router.post("/deep-dive")
async def deep_dive_analysis(req: DeepDiveRequest):
    """Premium deep-dive analysis streamed as SSE."""
    ticker = req.ticker.upper()
    return StreamingResponse(
        deep_dive_generator(ticker),
        media_type="text/event-stream"
    )

