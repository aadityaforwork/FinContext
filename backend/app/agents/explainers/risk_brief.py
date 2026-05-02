"""
Risk-brief explainer (Phase 2)
==============================
Single-agent crew that narrates a pre-computed risk + concentration report
from services.portfolio_analytics.

The agent receives RISK_REPORT as the task input — it does NOT call any tools
to fetch numbers. Numbers are deterministic; the agent's only job is
interpretation. Output is a structured Pydantic model so the router gets a
typed dict.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, Field

from app.agents.registry import make_risk_analyst
from app.services import llm_cache

# 24h TTL — overnight prices change once. Same holdings + same date = same brief.
_RISK_BRIEF_TTL_SECONDS = 24 * 3600


class _Observation(BaseModel):
    text: str
    source: str  # field path in RISK_REPORT, e.g. "metrics.beta_vs_nifty50"


class RiskBriefOutput(BaseModel):
    summary: str
    observations: list[_Observation] = Field(default_factory=list)
    risks: list[_Observation] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "low"
    data_gaps: list[str] = Field(default_factory=list)


def _build_crew():
    from crewai import Crew, Process, Task  # type: ignore

    analyst = make_risk_analyst()

    narrate_task = Task(
        description=(
            "Read the RISK_REPORT below and produce a structured brief.\n\n"
            "Required output fields (all citing RISK_REPORT field paths):\n"
            " - summary: ONE sentence describing the portfolio's overall risk posture.\n"
            " - observations: 3-5 items, each {text, source}. Cover at minimum: volatility, "
            "beta, max drawdown (worst window), Sharpe, sector concentration. SKIP any metric "
            "that is null in RISK_REPORT (add to data_gaps instead).\n"
            " - risks: 0-3 items flagging genuine concerns (e.g. high HHI, dangerous "
            "correlation cluster, deep drawdown). Each {text, source}.\n"
            " - confidence: 'high' only if every numeric field in metrics is non-null and "
            "sample_size_days >= 250; 'low' if more than half are null.\n"
            " - data_gaps: copy RISK_REPORT.data_gaps and append any null-metric notes.\n\n"
            "RULES:\n"
            "(1) Do NOT recompute or restate metrics with different rounding.\n"
            "(2) Do NOT invent a number that isn't in RISK_REPORT.\n"
            "(3) Phrase as educational signals, not advice. The user is unregistered with SEBI.\n\n"
            "RISK_REPORT:\n{risk_report}"
        ),
        expected_output=(
            "A single JSON object matching the RiskBriefOutput schema. No markdown."
        ),
        agent=analyst,
        output_pydantic=RiskBriefOutput,
    )

    return Crew(
        agents=[analyst],
        tasks=[narrate_task],
        process=Process.sequential,
        verbose=False,
    )


def _cache_key(report: dict) -> str:
    """Cache by content of the numeric report — same numbers => same brief."""
    canon = json.dumps(report.get("metrics", {}), sort_keys=True, default=str)
    canon += json.dumps(report.get("concentration", {}), sort_keys=True, default=str)
    digest = hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]
    return llm_cache.make_key("risk_brief", digest)


async def run(risk_report: dict) -> dict:
    """Run the risk-brief crew (cached). Returns the RiskBriefOutput dict."""
    from app.agents.orchestrator import run_cached

    return await run_cached(
        cache_key=_cache_key(risk_report),
        ttl_seconds=_RISK_BRIEF_TTL_SECONDS,
        builder=_build_crew,
        inputs={"risk_report": json.dumps(risk_report, default=str)},
        scope="global",
    )
