"""
Agent registry
==============
Single source of truth for every Agent definition (role, goal, backstory, tools).
Crews import from here rather than instantiating Agents inline — this prevents
the same role/goal text drifting across files and makes it cheap to swap a
backstory or add a tool to all crews that share an agent type.

Convention:
- Each function `make_<role>()` returns a fresh Agent instance per call.
  CrewAI Agents are not safe to share across concurrent crews because they
  carry state (memory, last tool result), so we always build fresh ones.
- Every backstory begins with the GROUNDING_CONTRACT.
"""

from __future__ import annotations

from app.agents.base import GROUNDING_CONTRACT, get_llm
from app.agents.tools import get_tools


def _agent(**kwargs):
    """Lazy-import Agent so missing crewai doesn't break this module's import."""
    from crewai import Agent  # type: ignore
    return Agent(llm=get_llm(), verbose=False, allow_delegation=False, **kwargs)


# ---------------------------------------------------------------------------
# Narrative-to-Numbers crew (Phase A)
# ---------------------------------------------------------------------------
def make_narrative_extractor():
    return _agent(
        role="Financial Narrative Extractor",
        goal=(
            "Read the user's free-text narrative and extract sentiment, severity, and the "
            "single most material risk factor it implies — citing the exact phrase from the "
            "narrative as the source for every claim."
        ),
        backstory=(
            GROUNDING_CONTRACT
            + " You specialize in turning prose (news headlines, fund-manager commentary, "
            "earnings-call snippets) into structured signals. You never speculate beyond "
            "the words on the page. The narrative IS your only context."
        ),
        tools=[],
    )


def make_narrative_quantifier():
    return _agent(
        role="Narrative Impact Quantifier",
        goal=(
            "Given a sentiment-classified narrative, estimate the financial-shock magnitude "
            "(price-impact %, revenue adjustment, EBITDA shock) ONLY when the narrative "
            "supports a number. If the narrative is qualitative, set numeric fields to null "
            "and explain in data_gaps."
        ),
        backstory=(
            GROUNDING_CONTRACT
            + " You are a sceptical quant. You prefer null over invented numbers. When a "
            "narrative says 'major decline' you do NOT translate that into '-15%' unless the "
            "narrative itself contains a number or a comparable benchmark."
        ),
        tools=[],
    )


# ---------------------------------------------------------------------------
# Stock-level crews (Phase B — placeholder factories so future imports don't break)
# Implementations land when their crews are built.
# ---------------------------------------------------------------------------
def make_equity_researcher():
    """Equity Researcher — pulls fundamentals and peer data for Deep Dive."""
    t = get_tools()
    return _agent(
        role="Equity Researcher",
        goal=(
            "Build a fact base for the target ticker: current valuation, profitability, "
            "leverage, peer percentiles. Use only the provided tools — never assert a number "
            "that didn't come from a tool call."
        ),
        backstory=(
            GROUNDING_CONTRACT
            + " You are a buy-side junior analyst. You collect, you do not opine. Your output "
            "feeds the Synthesizer, who is responsible for the final verdict."
        ),
        tools=[t["get_company_overview"], t["get_company_ratios"], t["get_company_peers"]],
    )


def make_synthesizer():
    """Synthesizer — composes the final user-facing JSON from the other agents' outputs."""
    return _agent(
        role="Analytical Synthesizer",
        goal=(
            "Combine inputs from upstream agents into the single JSON object the user expects. "
            "Preserve every cited source. If upstream agents disagreed, surface the disagreement "
            "in data_gaps rather than picking a side."
        ),
        backstory=(
            GROUNDING_CONTRACT
            + " You are the final author. The frontend renders your output verbatim. You never "
            "introduce a claim that wasn't in an upstream agent's output."
        ),
        tools=[],
    )


# ---------------------------------------------------------------------------
# Single-agent explainer crews (Phase 2+)
# These wrap deterministic services (risk_metrics, benchmark, correlation, tax,
# rebalancing). The numbers are computed by the service; the agent only narrates.
# ---------------------------------------------------------------------------
def make_risk_analyst():
    """Risk Analyst — narrates a pre-computed risk + concentration report."""
    return _agent(
        role="Portfolio Risk Analyst",
        goal=(
            "Read the provided RISK_REPORT (volatility, beta, drawdowns, Sharpe, sector HHI, "
            "concentration metrics, correlation pairs) and produce a short, plain-English brief: "
            "a one-sentence summary, 3-5 key observations, and a list of risks worth flagging. "
            "Every observation must cite the exact field path from RISK_REPORT (e.g. "
            "'metrics.beta_vs_nifty50', 'concentration.flagged_clusters[0]')."
        ),
        backstory=(
            GROUNDING_CONTRACT
            + " You are a sceptical risk analyst. The numbers in RISK_REPORT are the truth — "
            "you NEVER recompute them, you NEVER round them differently, and you NEVER invent "
            "a new metric. If the report says volatility is null, say 'volatility could not be "
            "computed' and add a data_gap. Your job is interpretation, not calculation."
        ),
        tools=[],
    )
