"""
Risk router (Phase 2)
=====================
Exposes portfolio-level risk + concentration metrics computed by
services.portfolio_analytics, then narrates them via the risk-brief explainer
crew when the agent stack is available.

Architectural notes:
- Numbers ALWAYS come from the deterministic service. Even if the agent fails,
  the metrics are returned — the explanation just gets a fallback summary.
- Compliance: every response wrapped in with_disclaimer (Phase 1 contract).
- Caching: the explainer crew handles its own cache via the orchestrator.
  The numeric report is fast enough on cache-hit (price history is cached
  in services.market_data and portfolio_analytics for 30 min).
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agents import base as agents_base
from app.agents.explainers import risk_brief as risk_brief_crew
from app.core.compliance import with_disclaimer
from app.services import portfolio_analytics

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/risk", tags=["risk"])


class _PositionIn(BaseModel):
    ticker: str
    quantity: float
    buy_price: float


class RiskRequest(BaseModel):
    positions: list[_PositionIn]


def _deterministic_explanation(report: dict) -> dict:
    """Fallback explanation when the agent stack is unavailable.

    Generates a couple of factual observations directly from the report so
    the frontend always has something to render.
    """
    metrics = report.get("metrics", {}) or {}
    conc = report.get("concentration", {}) or {}
    obs: list[dict] = []
    if metrics.get("volatility_annualized") is not None:
        obs.append({
            "text": f"Annualized portfolio volatility ≈ {metrics['volatility_annualized'] * 100:.1f}%.",
            "source": "metrics.volatility_annualized",
        })
    if metrics.get("beta_vs_nifty50") is not None:
        obs.append({
            "text": f"Beta vs NIFTY 50 ≈ {metrics['beta_vs_nifty50']:.2f}.",
            "source": "metrics.beta_vs_nifty50",
        })
    if metrics.get("sharpe_ratio") is not None:
        obs.append({
            "text": f"Sharpe ratio ≈ {metrics['sharpe_ratio']:.2f} (rf = {metrics.get('risk_free_rate_used', 0.06):.1%}).",
            "source": "metrics.sharpe_ratio",
        })
    if conc.get("sector_hhi") is not None:
        obs.append({
            "text": f"Sector HHI = {conc['sector_hhi']:.2f} (1.00 = single sector).",
            "source": "concentration.sector_hhi",
        })
    return {
        "summary": "Numeric report only — agent narration unavailable.",
        "observations": obs,
        "risks": [
            {"text": c, "source": "concentration.flagged_clusters"}
            for c in (conc.get("flagged_clusters") or [])[:3]
        ],
        "confidence": "low",
        "data_gaps": list(report.get("data_gaps") or []) + ["agent narration disabled"],
    }


@router.post("/metrics")
async def compute_risk_metrics(req: RiskRequest):
    """Compute portfolio risk metrics + concentration + correlation.

    Pipeline:
      1. services.portfolio_analytics.compute_risk_brief — deterministic numbers
      2. agents.explainers.risk_brief — agent narration (cached)
      3. with_disclaimer envelope
    """
    if not req.positions:
        raise HTTPException(status_code=400, detail="positions list is empty")

    raw_positions = [{"ticker": p.ticker.upper(), "quantity": p.quantity, "buy_price": p.buy_price}
                     for p in req.positions]

    # Step 1: deterministic math (off-loop because of network I/O).
    try:
        report = await asyncio.to_thread(portfolio_analytics.compute_risk_brief, raw_positions)
    except Exception:
        logger.exception("risk_brief computation failed")
        raise HTTPException(status_code=500, detail="risk computation failed")

    # Step 2: agent narration with graceful fallback.
    explanation: dict
    if agents_base.is_available():
        try:
            agent_out = await risk_brief_crew.run(report)
            if agent_out:
                explanation = agent_out
            else:
                logger.warning("risk-brief crew returned empty; using deterministic explanation")
                explanation = _deterministic_explanation(report)
        except Exception:
            logger.exception("risk-brief crew failed; using deterministic explanation")
            explanation = _deterministic_explanation(report)
    else:
        explanation = _deterministic_explanation(report)

    return with_disclaimer({
        "metrics": report["metrics"],
        "concentration": report["concentration"],
        "correlations": report["correlations"],
        "holdings_value": report["holdings_value"],
        "explanation": explanation,
        "data_gaps": report["data_gaps"],
    })
