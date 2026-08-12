"""
Prompt Monitor Router
======================
Admin-token endpoint for the Phase 3 online prompt-version monitor (path-
back leg 3b). Same shape as /api/outcomes/compute-daily: POST, gated by
X-Admin-Token, designed to be hit by an external cron once a day, idempotent.

  POST /api/prompt-monitor/run-daily  → run prompt_monitor.evaluate() for
                                         every monitored prompt. Protected
                                         by X-Admin-Token.

NEVER PROMOTES. The only Langfuse write this can trigger is a revert to a
previously-live version — see prompt_monitor.py's module docstring /
AGENTS.md ("forward promotion is a human action").
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Header

from app.routers.outcomes import _check_admin  # reuse the existing ADMIN_TOKEN check — no new env read
from app.services import prompt_monitor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/prompt-monitor", tags=["prompt-monitor"])


@router.post("/run-daily")
async def run_daily(x_admin_token: str | None = Header(default=None)):
    """Run the daily prompt-version comparison for every monitored prompt
    (prompt_monitor.MONITORED_PROMPTS). Idempotent — safe to re-run any
    time; see prompt_monitor.py's module docstring for why a second
    consecutive run after a revert is naturally a no-op rather than
    reverting again.

    Returns one result per prompt, each carrying an `action` + `reason` —
    every decision is reported, including no-ops (see prompt_monitor.
    evaluate()'s docstring for the full action vocabulary).
    """
    _check_admin(x_admin_token)
    results = {}
    for name in prompt_monitor.MONITORED_PROMPTS:
        # evaluate() itself never raises, but this loop must not let one
        # prompt's unexpected failure take the others down with it.
        try:
            results[name] = prompt_monitor.evaluate(name)
        except Exception as e:
            logger.exception("prompt-monitor run-daily: %s failed unexpectedly", name)
            results[name] = {"prompt_name": name, "action": "error", "reason": str(e)}
    return results
