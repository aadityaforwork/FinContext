"""Admin endpoint for the independent grounding-contract monitor."""

from __future__ import annotations

from fastapi import APIRouter, Header

from app.routers.outcomes import _check_admin
from app.services.pathback import grounding_monitor

router = APIRouter(prefix="/api/grounding-monitor", tags=["grounding-monitor"])


@router.post("/run-daily")
async def run_daily(x_admin_token: str | None = Header(default=None)):
    _check_admin(x_admin_token)
    return grounding_monitor.run_all()
