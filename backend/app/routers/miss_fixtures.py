"""
Miss Fixtures Router
======================
POST /api/miss-fixtures/run-daily — daily idempotent job (path-back leg 3d)
converting recently graded market misses into permanent eval fixtures — see
app/services/miss_fixtures.py's module docstring for the full design and
why the context these fixtures replay never touches a publicly-readable
table.

Protected by the same X-Admin-Token as the other three daily jobs
(/api/outcomes/compute-daily, /api/prompt-monitor/run-daily,
/api/accuracy-monitor/run-daily). Run this AFTER compute-daily so today's
predictions are graded before this job looks for misses.
"""

from __future__ import annotations

from fastapi import APIRouter, Header

from app.routers.outcomes import _check_admin
from app.services.pathback import miss_fixtures

router = APIRouter(prefix="/api/miss-fixtures", tags=["miss-fixtures"])


@router.post("/run-daily")
async def run_daily(x_admin_token: str | None = Header(default=None)):
    _check_admin(x_admin_token)
    return miss_fixtures.convert_pending_misses()
