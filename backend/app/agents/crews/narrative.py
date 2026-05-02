"""
Narrative-to-Numbers crew (Phase A — first migrated workflow)
=============================================================
Given a free-text narrative (news headline, manager commentary, etc.), produce
a structured financial-shock estimate. The narrative IS the only context — no
external tools.

Two-agent sequential crew:
  1. Extractor   — sentiment, severity, risk factor (qualitative)
  2. Quantifier  — price impact %, revenue/EBITDA adjustment (numeric, often null)

Output shape matches the legacy /api/analysis/narrative-impact response so the
frontend doesn't need to change.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, Field

from app.agents.registry import make_narrative_extractor, make_narrative_quantifier
from app.services import llm_cache

# Cache narrative analyses for 24h. Same text → same answer.
_NARRATIVE_TTL_SECONDS = 24 * 3600


class _RiskFactor(BaseModel):
    text: str
    source: Literal["narrative"] = "narrative"


class NarrativeOutput(BaseModel):
    """Final crew output. Mirrors the legacy schema used by the frontend."""
    sentiment: Literal["Positive", "Negative", "Neutral"]
    severity_1_to_10: int | None = Field(default=None, ge=0, le=10)
    estimated_price_impact_percent: float | None = None
    algorithmic_action: Literal["Sell/Hedge", "Accumulate", "Hold"] = "Hold"
    revenue_adjustment: str | None = None
    ebitda_shock: str | None = None
    risk_factor: _RiskFactor
    confidence: Literal["low", "medium", "high"] = "low"
    data_gaps: list[str] = Field(default_factory=list)


def _build_crew():
    """Build a fresh crew. Lazy import keeps app.routers free of crewai unless used."""
    from crewai import Crew, Process, Task  # type: ignore

    extractor = make_narrative_extractor()
    quantifier = make_narrative_quantifier()

    extract_task = Task(
        description=(
            "Read the NARRATIVE below and extract:\n"
            " - sentiment: Positive / Negative / Neutral\n"
            " - severity_1_to_10: integer (or null if narrative is non-actionable)\n"
            " - the single most material risk factor as {text, source:'narrative'}\n"
            "Quote the exact phrase from the narrative as the `text` of the risk factor.\n\n"
            "NARRATIVE:\n{narrative}"
        ),
        expected_output=(
            "A short JSON object with keys sentiment, severity_1_to_10, risk_factor, "
            "and a list of data_gaps for anything the narrative did not cover."
        ),
        agent=extractor,
    )

    quantify_task = Task(
        description=(
            "Using the prior task's output AND the original NARRATIVE, estimate the financial "
            "impact. Set fields to null when the narrative does not contain enough to support "
            "a number — do NOT translate qualitative phrases into numbers.\n\n"
            "Required fields:\n"
            " - estimated_price_impact_percent (float | null)\n"
            " - algorithmic_action: Sell/Hedge | Accumulate | Hold (mapped from sentiment + severity)\n"
            " - revenue_adjustment: brief string like '-3% to -5% topline' or null\n"
            " - ebitda_shock: brief string or null\n"
            " - confidence: low | medium | high\n"
            " - data_gaps: list[str]\n"
            "Carry over sentiment, severity_1_to_10, and risk_factor from the prior task verbatim.\n\n"
            "NARRATIVE:\n{narrative}"
        ),
        expected_output=(
            "A single JSON object matching the NarrativeOutput schema. No markdown, no commentary."
        ),
        agent=quantifier,
        context=[extract_task],
        output_pydantic=NarrativeOutput,
    )

    return Crew(
        agents=[extractor, quantifier],
        tasks=[extract_task, quantify_task],
        process=Process.sequential,
        verbose=False,
    )


def _cache_key(narrative: str) -> str:
    digest = hashlib.sha256(narrative.encode("utf-8")).hexdigest()[:16]
    return llm_cache.make_key("narrative", digest)


async def run(narrative: str) -> dict:
    """Run the crew (cached). Returns the legacy router response shape, minus the disclaimer.

    The router is responsible for wrapping the result in `with_disclaimer` and
    framing it inside the response envelope (`source_text`, `extraction`, ...).
    """
    from app.agents.orchestrator import run_cached

    return await run_cached(
        cache_key=_cache_key(narrative),
        ttl_seconds=_NARRATIVE_TTL_SECONDS,
        builder=_build_crew,
        inputs={"narrative": narrative},
        scope="global",
    )
