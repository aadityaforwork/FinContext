"""
Prompt Drafter Router
========================
Two admin-token-gated endpoints, path-back leg 3e:

  POST /api/prompt-drafter/run-pending     — scan the independent market-
      accuracy and grounding-contract alert queues and kick off a draft-test-approve
      run for each one not already covered by an in-flight/recent attempt.
      Run AFTER accuracy-monitor/run-daily so today's alerts (if any) are
      already logged.

  POST /api/prompt-drafter/check-approvals — for every run paused waiting
      on a human, check whether the Langfuse `production` label has been
      moved to that run's candidate version; if so, resume the graph and
      close the loop. Safe to run on a much shorter interval than the daily
      crons (checking is cheap and read-only) — every other job in this
      family runs once/day, this one's fine on the same schedule too.

Never writes a Langfuse label itself — see prompt_drafter.py's module
docstring. Same X-Admin-Token gate as every other path-back cron.
"""

from __future__ import annotations

from fastapi import APIRouter, Header

from app.routers.outcomes import _check_admin
from app.services.pathback import prompt_drafter

router = APIRouter(prefix="/api/prompt-drafter", tags=["prompt-drafter"])


@router.post("/run-pending")
async def run_pending(x_admin_token: str | None = Header(default=None)):
    _check_admin(x_admin_token)
    return prompt_drafter.run_pending_drafts()


@router.post("/check-approvals")
async def check_approvals(x_admin_token: str | None = Header(default=None)):
    _check_admin(x_admin_token)
    return prompt_drafter.check_pending_approvals()
