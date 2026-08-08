"""
Deterministic grounding tests — no API key required, run in CI on every push.

These don't call an LLM. They lock down the parts of the grounding pipeline
that are pure Python: the disclaimer helper, the signal ensemble, and the
Pydantic schemas the crews are contractually required to fill in. If one of
these breaks, a live LLM eval further down the pipeline would fail too but
take longer and cost money to find out — catch it here first.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agents.crews.narrative import NarrativeOutput
from app.agents.explainers.risk_brief import RiskBriefOutput
from app.core.compliance import DISCLAIMER_TEXT, with_disclaimer
from app.services import signal_ensemble


# ---------------------------------------------------------------------------
# Compliance
# ---------------------------------------------------------------------------
def test_with_disclaimer_attaches_text():
    payload = with_disclaimer({"verdict": "accumulate_signal"})
    assert payload["disclaimer"] == DISCLAIMER_TEXT
    assert "disclaimer_short" in payload


def test_with_disclaimer_is_idempotent():
    """Calling twice must not duplicate or overwrite a caller-provided disclaimer."""
    once = with_disclaimer({"a": 1})
    twice = with_disclaimer(once)
    assert once is twice
    assert twice["disclaimer"] == DISCLAIMER_TEXT


def test_with_disclaimer_non_dict_passthrough():
    assert with_disclaimer("not a dict") == "not a dict"  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Signal ensemble — selectivity over coverage
# ---------------------------------------------------------------------------
def test_ensemble_no_signals_returns_neutral_50():
    result = signal_ensemble.compute_ensemble(None, None, None, None)
    assert result["consensus_direction"] == "neutral"
    assert result["conviction"] == 50
    assert result["signal_count"] == 0


def test_ensemble_all_signals_agree_positive_high_conviction():
    result = signal_ensemble.compute_ensemble(
        news_direction="positive",
        technicals={"momentum_state": "extending_up", "sma_state": "above_sma50", "rsi_zone": "strong"},
        sector_change_pct=2.0,
        flows={"fii_net_cr": 2000, "dii_net_cr": 500},
    )
    assert result["consensus_direction"] == "positive"
    assert result["conviction"] > 50
    assert result["conflicting_signals"] == 0


def test_ensemble_conflicting_signals_cap_conviction():
    """News says positive, technicals say negative — conviction must not be high."""
    result = signal_ensemble.compute_ensemble(
        news_direction="positive",
        technicals={"momentum_state": "extending_down", "sma_state": "below_sma50"},
        sector_change_pct=None,
        flows=None,
    )
    assert result["conflicting_signals"] >= 1
    assert result["conviction"] <= 65


def test_ensemble_conviction_never_exceeds_95():
    """Markets are never fully predictable — hard ceiling regardless of agreement."""
    result = signal_ensemble.compute_ensemble(
        news_direction="positive",
        technicals={"momentum_state": "extending_up", "sma_state": "above_sma50", "rsi_zone": "strong"},
        sector_change_pct=5.0,
        flows={"fii_net_cr": 5000, "dii_net_cr": 5000},
    )
    assert result["conviction"] <= 95


def test_ensemble_missing_news_caps_conviction_at_65():
    """Technicals + sector alone (no news catalyst) shouldn't carry a high-conviction call."""
    result = signal_ensemble.compute_ensemble(
        news_direction=None,
        technicals={"momentum_state": "extending_up", "sma_state": "above_sma50", "rsi_zone": "strong"},
        sector_change_pct=3.0,
        flows={"fii_net_cr": 3000, "dii_net_cr": 3000},
    )
    assert result["conviction"] <= 65


# ---------------------------------------------------------------------------
# Crew output schemas — the contract the router relies on
# ---------------------------------------------------------------------------
def test_narrative_output_rejects_severity_out_of_range():
    with pytest.raises(ValidationError):
        NarrativeOutput(
            sentiment="Negative",
            severity_1_to_10=15,  # out of 0-10 range
            risk_factor={"text": "x", "source": "narrative"},
        )


def test_narrative_output_allows_null_numeric_fields():
    """The whole point of the grounding contract: null is a valid, expected answer."""
    out = NarrativeOutput(
        sentiment="Neutral",
        severity_1_to_10=None,
        estimated_price_impact_percent=None,
        revenue_adjustment=None,
        ebitda_shock=None,
        risk_factor={"text": "no material risk identified", "source": "narrative"},
        confidence="low",
        data_gaps=["narrative contained no quantifiable claim"],
    )
    assert out.estimated_price_impact_percent is None
    assert out.confidence == "low"


def test_risk_brief_output_rejects_bare_string_observation():
    """Observations must be {text, source} objects, never bare strings — this is
    what makes every claim traceable back to a RISK_REPORT field path."""
    with pytest.raises(ValidationError):
        RiskBriefOutput(summary="ok", observations=["volatility is fine"])  # type: ignore[list-item]


def test_risk_brief_output_requires_source_on_observations():
    out = RiskBriefOutput(
        summary="Moderate risk with elevated sector concentration.",
        observations=[{"text": "Beta of 1.12 vs NIFTY 50.", "source": "metrics.beta_vs_nifty50"}],
        risks=[{"text": "Top sector at 42% is above the 35% comfort band.", "source": "concentration.top_sector_pct"}],
        confidence="medium",
        data_gaps=["Sharpe ratio requires 250+ trading days; only 40 available."],
    )
    assert out.observations[0].source == "metrics.beta_vs_nifty50"
