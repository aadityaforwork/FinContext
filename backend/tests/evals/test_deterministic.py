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
from app.services import prompt_registry, signal_ensemble, track_record


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
# Track record calibration — path-back signal #1 (fastest + most specific).
# outcome_ledger.scored_rows() is monkeypatched everywhere here — no Supabase
# client needed, and the module-level segment cache is cleared around every
# test so results from one test can't leak into the next.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _clear_track_record_cache():
    track_record._cache.clear()
    yield
    track_record._cache.clear()


def _scored_rows(n_hits: int, n_total: int, source="news_feed", catalyst_type="earnings"):
    rows = [{"source": source, "catalyst_type": catalyst_type, "hit": True} for _ in range(n_hits)]
    rows += [{"source": source, "catalyst_type": catalyst_type, "hit": False} for _ in range(n_total - n_hits)]
    return rows


def test_track_record_no_data_anywhere_is_a_noop(monkeypatch):
    """Zero-data limit of the shrinkage formula must reproduce the old
    cold-start behavior exactly: no history anywhere -> factor 1.0."""
    monkeypatch.setattr(track_record.outcome_ledger, "scored_rows", lambda **kw: [])
    cal = track_record.calibration_factor("news_feed", "earnings")
    assert cal["factor"] == 1.0
    assert cal["pair_n"] == 0
    assert cal["source_n"] == 0
    assert cal["global_n"] == 0


def test_track_record_pair_level_good_history_boosts_factor(monkeypatch):
    monkeypatch.setattr(track_record.outcome_ledger, "scored_rows", lambda **kw: _scored_rows(18, 20))  # 90% hits
    cal = track_record.calibration_factor("news_feed", "earnings")
    assert cal["pair_n"] == 20
    assert 1.0 < cal["factor"] <= track_record.FACTOR_CEIL


def test_track_record_pair_level_bad_history_discounts_factor(monkeypatch):
    monkeypatch.setattr(track_record.outcome_ledger, "scored_rows", lambda **kw: _scored_rows(2, 20))  # 10% hits
    cal = track_record.calibration_factor("news_feed", "earnings")
    assert track_record.FACTOR_FLOOR <= cal["factor"] < 1.0


def test_track_record_coin_flip_hit_rate_is_neutral(monkeypatch):
    monkeypatch.setattr(track_record.outcome_ledger, "scored_rows", lambda **kw: _scored_rows(10, 20))  # 50%
    cal = track_record.calibration_factor("news_feed", "earnings")
    assert cal["factor"] == 1.0


def test_track_record_thin_sample_is_pulled_toward_parent_not_taken_at_face_value(monkeypatch):
    """3/10 (30%) is an ordinary result for a truly 50%-skill segment. With the
    old hard-cliff design this got a real discount off pure noise. Shrinkage
    must pull it most of the way back toward the parent tiers' rate.

    Background rows on a *different* catalyst_type (roughly coin-flip) keep
    source/global near-neutral, isolating what the pair-level shrink alone
    does to the thin, noisy 30% sample — without this, source/global would
    just collapse onto the same 10 noisy rows since they'd be the only data
    in the fixture, and the test would stop isolating what it claims to.
    """
    background = _scored_rows(50, 100, catalyst_type="technical")  # stable ~50%
    thin_noisy_pair = _scored_rows(3, 10, catalyst_type="earnings")
    monkeypatch.setattr(track_record.outcome_ledger, "scored_rows", lambda **kw: background + thin_noisy_pair)
    cal = track_record.calibration_factor("news_feed", "earnings")
    raw_factor = track_record._factor_from_rate(0.30)
    assert cal["factor"] > raw_factor
    assert cal["factor"] > 0.9  # pulled back close to neutral, not left at the noisy raw estimate


def test_track_record_no_cliff_at_old_threshold_boundary(monkeypatch):
    """Same hit-rate (~30%) at n=9 vs n=11 — straddling the old hard
    MIN_SAMPLE=10 cutoff — must produce close, monotonically-ordered
    factors, not a jump. Background rows (see previous test) keep the
    parent tiers stable so this isolates the pair-level cliff specifically."""
    background = _scored_rows(50, 100, catalyst_type="technical")
    monkeypatch.setattr(
        track_record.outcome_ledger, "scored_rows",
        lambda **kw: background + _scored_rows(3, 9, catalyst_type="earnings"),
    )
    factor_below = track_record.calibration_factor("news_feed", "earnings")["factor"]
    track_record._cache.clear()
    monkeypatch.setattr(
        track_record.outcome_ledger, "scored_rows",
        lambda **kw: background + _scored_rows(3, 11, catalyst_type="earnings"),
    )
    factor_above = track_record.calibration_factor("news_feed", "earnings")["factor"]
    assert abs(factor_above - factor_below) < 0.03  # smooth, not a cliff
    assert factor_above <= factor_below  # more (still-losing) data -> at least as discounted


def test_track_record_falls_back_toward_source_when_pair_thin(monkeypatch):
    """Pair (news_feed, earnings) is sparse; the source overall (earnings +
    technical combined) is healthy and good. The pair's blended estimate
    should sit between its own raw rate and the source's rate — pulled
    toward the source, not stuck at the tiny pair sample alone."""
    rows = (
        _scored_rows(2, 3, catalyst_type="earnings")   # pair: 2/3, noisy
        + _scored_rows(18, 20, catalyst_type="technical")  # source-wide: mostly this, strong
    )
    monkeypatch.setattr(track_record.outcome_ledger, "scored_rows", lambda **kw: rows)
    cal = track_record.calibration_factor("news_feed", "earnings")
    assert cal["pair_n"] == 3
    assert cal["source_n"] == 23
    # pulled up from the pair's raw 2/3 toward the strong source-wide rate
    assert cal["factor"] > track_record._factor_from_rate(2 / 3)


def test_track_record_calibrate_preserves_direction_only_scales_conviction(monkeypatch):
    monkeypatch.setattr(track_record.outcome_ledger, "scored_rows", lambda **kw: _scored_rows(2, 20))  # bad history
    ensemble = {"consensus_direction": "positive", "conviction": 80, "breakdown": {}}
    out = track_record.calibrate(ensemble, source="news_feed", catalyst_type="earnings")
    assert out["consensus_direction"] == "positive"  # calibration never touches direction
    assert out["raw_conviction"] == 80
    assert out["conviction"] < 80
    assert 0 <= out["conviction"] <= 95


def test_track_record_calibrate_never_raises_on_backend_failure(monkeypatch):
    def _boom(**kw):
        raise RuntimeError("supabase down")

    monkeypatch.setattr(track_record.outcome_ledger, "scored_rows", _boom)
    ensemble = {"consensus_direction": "neutral", "conviction": 50, "breakdown": {}}
    out = track_record.calibrate(ensemble, source="news_feed", catalyst_type="earnings")
    assert out["conviction"] == 50
    assert out["calibration_pair_n"] == 0


# ---------------------------------------------------------------------------
# Prompt registry — path-back signal #2 (Langfuse-managed prompts, leg 3b).
# langfuse_client.get_client() is monkeypatched everywhere here -- no real
# Langfuse SDK/network call happens in any of these tests.
# ---------------------------------------------------------------------------
class _FakePromptClient:
    """Stands in for langfuse.model.TextPromptClient."""

    def __init__(self, prompt: str, version: int | None = None, is_fallback: bool = False):
        self.prompt = prompt
        self.version = version
        self.is_fallback = is_fallback


class _FakeLangfuseClient:
    """Stands in for the Langfuse SDK client — records the kwargs it was
    called with so tests can assert the production label / cache TTL /
    fallback text were passed through correctly, and can be told to return
    a canned prompt or raise."""

    def __init__(self, *, returns: _FakePromptClient | None = None, raises: Exception | None = None):
        self._returns = returns
        self._raises = raises
        self.calls: list[dict] = []

    def get_prompt(self, name, **kwargs):
        self.calls.append({"name": name, **kwargs})
        if self._raises is not None:
            raise self._raises
        return self._returns


def test_prompt_registry_no_langfuse_configured_returns_fallback(monkeypatch):
    monkeypatch.setattr(prompt_registry.langfuse_client, "get_client", lambda: None)
    result = prompt_registry.get_prompt("portfolio.tomorrow_watch", "FALLBACK TEXT")
    assert result.text == "FALLBACK TEXT"
    assert result.version is None
    assert result.source == "fallback_no_client"


def test_prompt_registry_returns_langfuse_prompt_when_available(monkeypatch):
    fake = _FakeLangfuseClient(returns=_FakePromptClient("LANGFUSE TEXT", version=3))
    monkeypatch.setattr(prompt_registry.langfuse_client, "get_client", lambda: fake)
    result = prompt_registry.get_prompt("portfolio.tomorrow_watch", "FALLBACK TEXT")
    assert result.text == "LANGFUSE TEXT"
    assert result.version == 3
    assert result.source == "langfuse"


def test_prompt_registry_requests_production_label_by_default(monkeypatch):
    """Code must never read the `candidate` label directly -- promotion to
    production is the human/eval review gate (see module docstring)."""
    fake = _FakeLangfuseClient(returns=_FakePromptClient("X", version=1))
    monkeypatch.setattr(prompt_registry.langfuse_client, "get_client", lambda: fake)
    prompt_registry.get_prompt("portfolio.news_feed_annotation", "FALLBACK")
    assert fake.calls[0]["label"] == "production"
    assert fake.calls[0]["fallback"] == "FALLBACK"
    assert fake.calls[0]["cache_ttl_seconds"] == prompt_registry.PROMPT_CACHE_TTL_SECONDS


def test_prompt_registry_sdk_level_fallback_is_labeled_distinctly(monkeypatch):
    """When Langfuse is configured but the fetch itself fails, the SDK's own
    `fallback=` kwarg returns a synthesized client with is_fallback=True --
    make sure that's distinguishable from a real fetch in the audit trail."""
    fake = _FakeLangfuseClient(returns=_FakePromptClient("FALLBACK TEXT", version=0, is_fallback=True))
    monkeypatch.setattr(prompt_registry.langfuse_client, "get_client", lambda: fake)
    result = prompt_registry.get_prompt("portfolio.tomorrow_watch", "FALLBACK TEXT")
    assert result.source == "fallback_sdk"
    assert result.version is None  # not a real version, don't record it as one


def test_prompt_registry_client_raising_outside_sdk_fallback_is_caught(monkeypatch):
    """The SDK raises unconditionally (before its own fallback logic) if the
    client itself isn't correctly initialized -- this module's own
    try/except is the outer safety net for that case."""
    fake = _FakeLangfuseClient(raises=RuntimeError("SDK is not correctly initialized"))
    monkeypatch.setattr(prompt_registry.langfuse_client, "get_client", lambda: fake)
    result = prompt_registry.get_prompt("portfolio.tomorrow_watch", "FALLBACK TEXT")
    assert result.text == "FALLBACK TEXT"
    assert result.version is None
    assert result.source == "fallback_error"


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
