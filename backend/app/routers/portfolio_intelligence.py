"""
Portfolio Intelligence Router
==============================
AI-powered portfolio analysis: health score, per-holding signals,
risk alerts, and stock recommendations — streamed via SSE.
"""

import asyncio
import json
import os
import google.generativeai as genai
from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.db.models import PortfolioPosition
from app.nse_universe import TICKER_TO_META

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
_model = None
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    _model = genai.GenerativeModel('gemini-2.0-flash')

router = APIRouter(prefix="/api/intelligence", tags=["portfolio-intelligence"])


async def _intelligence_generator(holdings: list[dict]):
    """Stream portfolio intelligence as SSE events."""

    yield f"data: {json.dumps({'type': 'step', 'message': 'Scanning portfolio holdings...'})}\n\n"
    await asyncio.sleep(0.4)

    yield f"data: {json.dumps({'type': 'step', 'message': f'Found {len(holdings)} stocks. Analyzing diversification...'})}\n\n"
    await asyncio.sleep(0.4)

    yield f"data: {json.dumps({'type': 'step', 'message': 'Evaluating sector concentration risk...'})}\n\n"
    await asyncio.sleep(0.4)

    yield f"data: {json.dumps({'type': 'step', 'message': 'Generating per-stock verdicts...'})}\n\n"
    await asyncio.sleep(0.3)

    yield f"data: {json.dumps({'type': 'step', 'message': 'Identifying better alternatives...'})}\n\n"
    await asyncio.sleep(0.3)

    yield f"data: {json.dumps({'type': 'step', 'message': 'Compiling final intelligence report...'})}\n\n"

    if not _model:
        yield f"data: {json.dumps({'type': 'step', 'message': 'ERROR: Gemini API key not configured.'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    holdings_summary = "\n".join([
        f"- {h['ticker']} ({h['name']}, {h['sector']}): {h['quantity']} shares @ ₹{h['buy_price']} avg"
        for h in holdings
    ])

    prompt = f"""You are an expert Indian equity portfolio strategist. Analyze this retail investor's portfolio and provide actionable intelligence.

PORTFOLIO:
{holdings_summary}

Respond ONLY with a valid JSON object with these exact keys:
- "portfolio_health_score": integer 1-100 (overall portfolio quality)
- "health_breakdown": object with keys "diversification" (1-100), "quality" (1-100), "risk" (1-100), "momentum" (1-100)
- "holdings_verdicts": array of objects, one per holding, each with:
  - "ticker": string
  - "signal": "BUY" or "HOLD" or "REDUCE"
  - "reason": string (1 short sentence)
  - "confidence": integer 1-100
- "top_risks": array of 3 objects, each with "title" (string) and "description" (string, 1 sentence)
- "recommendations": array of 3 objects, each with:
  - "ticker": string (NSE symbol, must be different from portfolio holdings)
  - "name": string (company name)
  - "sector": string
  - "rationale": string (1-2 sentences on why this stock complements the portfolio)
  - "conviction": "HIGH" or "MEDIUM"
"""

    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(_model.generate_content, prompt),
            timeout=30
        )
        text = response.text
        # Extract JSON
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        data = json.loads(text)

        result = {
            "type": "result",
            "portfolio_health_score": data.get("portfolio_health_score", 50),
            "health_breakdown": data.get("health_breakdown", {}),
            "holdings_verdicts": data.get("holdings_verdicts", []),
            "top_risks": data.get("top_risks", []),
            "recommendations": data.get("recommendations", []),
        }
        yield f"data: {json.dumps(result)}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'step', 'message': f'Analysis failed: {str(e)}'})}\n\n"

    yield "data: [DONE]\n\n"


@router.post("/portfolio")
async def portfolio_intelligence(db: AsyncSession = Depends(get_db)):
    """Stream AI-powered portfolio intelligence as SSE."""
    result = await db.execute(select(PortfolioPosition))
    rows = result.scalars().all()

    if not rows:
        return {"error": "No holdings found. Import your portfolio first."}

    holdings = []
    for pos in rows:
        meta = TICKER_TO_META.get(pos.ticker, {"name": pos.ticker, "sector": "Unknown"})
        holdings.append({
            "ticker": pos.ticker,
            "name": meta["name"],
            "sector": meta["sector"],
            "quantity": pos.quantity,
            "buy_price": pos.buy_price,
        })

    return StreamingResponse(
        _intelligence_generator(holdings),
        media_type="text/event-stream"
    )
