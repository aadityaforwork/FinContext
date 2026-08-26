"""
Accuracy Monitor Router
=========================
POST /api/accuracy-monitor/run-daily — daily idempotent job (path-back leg
3c) comparing each monitored source's recent market-graded hit rate against
its own trailing baseline and pushing a Telegram alert when it's dropped
past both the sample-size and effect-size thresholds in accuracy_monitor.py.

Alert-only: never writes a Langfuse label, never touches a prompt. A human
decides what (if anything) to do — see accuracy_monitor.py's module
docstring for why that judgment call stays human.

Protected by the same X-Admin-Token as /api/outcomes/compute-daily and
/api/prompt-monitor/run-daily.
"""

from __future__ import annotations

from fastapi import APIRouter, Header

from app.routers.outcomes import _check_admin
from app.services.pathback import accuracy_monitor

router = APIRouter(prefix="/api/accuracy-monitor", tags=["accuracy-monitor"])


@router.post("/run-daily")
async def run_daily(x_admin_token: str | None = Header(default=None)):
    """Evaluate every source in accuracy_monitor.SOURCE_TO_PROMPT. One
    source's unexpected failure doesn't take the others down — each call is
    individually wrapped, mirroring routers/prompt_monitor.py."""
    _check_admin(x_admin_token)
    results = {}
    for source in accuracy_monitor.SOURCE_TO_PROMPT:
        try:
            results[source] = accuracy_monitor.evaluate(source)
        except Exception as e:
            results[source] = {"source": source, "action": "error", "reason": str(e)}
    return results
