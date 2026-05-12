"""
Outcomes Router
===============
Public + admin endpoints for the outcome ledger (track record of AI predictions).

  GET  /api/outcomes/accuracy       → aggregate hit-rate stats. PUBLIC.
  GET  /api/outcomes/recent         → recent scored calls. PUBLIC.
  POST /api/outcomes/compute-daily  → fill in outcomes for due predictions.
                                      Protected by X-Admin-Token. Designed to be
                                      hit by an external cron service (cron-job.org)
                                      once a day after market close.

The accuracy + recent endpoints are intentionally PUBLIC — the whole point of
the ledger is to be social proof on a landing page. No auth, no scope.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Query

from app.services import outcome_ledger

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/outcomes", tags=["outcomes"])

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")


def _check_admin(token: str | None) -> None:
    if not ADMIN_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="ADMIN_TOKEN not configured on the server.",
        )
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid admin token.")


@router.get("/accuracy")
async def accuracy(
    horizon: str = Query("1d", description="1d | 5d | 20d"),
    source: str | None = Query(None, description="tomorrow_per_holding | news_feed"),
    impact_level: str | None = Query(None, description="high | medium | low"),
    days: int = Query(30, ge=1, le=365),
):
    """Aggregate accuracy stats for the chosen horizon over the last `days`
    days. Includes top-line hit rate plus breakdowns by impact / source /
    direction / catalyst type."""
    if not outcome_ledger.is_available():
        return {"error": "Outcome ledger not configured (Supabase missing).",
                "horizon": horizon, "days": days,
                "total": 0, "scored": 0, "hits": 0, "hit_rate_pct": None}
    return outcome_ledger.accuracy_summary(
        horizon=horizon, source=source, impact_level=impact_level, days=days
    )


@router.get("/recent")
async def recent(
    horizon: str = Query("1d"),
    limit: int = Query(30, ge=1, le=200),
):
    """Recent (prediction, outcome) rows for the Recent Calls table."""
    if not outcome_ledger.is_available():
        return {"items": [], "error": "Outcome ledger not configured."}
    return {
        "items": outcome_ledger.recent_results(limit=limit, horizon=horizon),
        "horizon": horizon,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/compute-daily")
async def compute_daily(x_admin_token: str | None = Header(default=None)):
    """Run the daily outcome-computation pass. Idempotent — only fills in pairs
    that don't already have a row. Designed to be hit by an external cron at
    ~4:30 PM IST (post NSE close + safety margin).

    Returns a summary: how many (prediction, horizon) pairs were processed,
    how many had enough trading days elapsed to score, how many were written.
    """
    _check_admin(x_admin_token)
    if not outcome_ledger.is_available():
        raise HTTPException(status_code=503, detail="Outcome ledger client unavailable.")
    summary = outcome_ledger.compute_pending_outcomes()
    return summary
