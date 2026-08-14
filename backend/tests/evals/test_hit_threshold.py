"""
Horizon-scaled hit threshold
============================
The grading rule (`outcome_ledger._hit_rule`) used to compare every horizon
against one flat 0.5% band. That silently broke the score in both directions
at once, and had NO test coverage at all — which is why it survived long
enough to make 90 days of graded history un-comparable across horizons:

  - 'neutral' calls got progressively harder to hit as the horizon grew (a
    stock staying inside +/-0.5% for 20 trading days basically never happens).
    Real measured history: 32.9% at 1d vs 11% at 5d.
  - 'positive'/'negative' calls got progressively FREE, since clearing a fixed
    0.5% over 20 days takes no skill. Real measured history: 38.8% at 1d vs
    52.1% at 5d.

The two distortions partly cancel in the headline number, so the 1d/5d/20d
rates all looked flatly similar (35/37/37%) while the per-direction breakdown
underneath pulled apart. These tests lock in the sqrt(trading-days) scaling
and — more importantly — the property that made the old bug invisible: the
SAME return must be able to grade differently at different horizons.

Deterministic; no Supabase / network / LLM.
"""

from __future__ import annotations

import math

import pytest

from app.services import outcome_ledger as ol


# ---------------------------------------------------------------------------
# The threshold itself
# ---------------------------------------------------------------------------
def test_one_day_threshold_is_the_documented_base():
    assert ol.hit_threshold_pct("1d") == ol.HIT_THRESHOLD_PCT_1D == 0.5


@pytest.mark.parametrize("horizon,trading_days", [("1d", 1), ("5d", 5), ("20d", 20)])
def test_threshold_scales_as_sqrt_of_trading_days(horizon, trading_days):
    expected = ol.HIT_THRESHOLD_PCT_1D * math.sqrt(trading_days)
    assert ol.hit_threshold_pct(horizon) == pytest.approx(expected, abs=1e-4)


def test_threshold_is_strictly_increasing_with_horizon():
    """The whole point. If this ever flattens, the old bug is back."""
    assert (
        ol.hit_threshold_pct("1d")
        < ol.hit_threshold_pct("5d")
        < ol.hit_threshold_pct("20d")
    )


def test_threshold_is_derived_from_horizons_td_not_hardcoded():
    """Adding a horizon to HORIZONS_TD must not leave a stale threshold
    behind — so every declared horizon has to produce the sqrt scaling."""
    for horizon, td in ol.HORIZONS_TD.items():
        assert ol.hit_threshold_pct(horizon) == pytest.approx(
            ol.HIT_THRESHOLD_PCT_1D * math.sqrt(td), abs=1e-4
        )


def test_unknown_horizon_falls_back_to_base_rather_than_raising():
    """The daily grading job must not crash on an unexpected horizon label."""
    assert ol.hit_threshold_pct("does-not-exist") == ol.HIT_THRESHOLD_PCT_1D


# ---------------------------------------------------------------------------
# _hit_rule — the property the old flat constant destroyed
# ---------------------------------------------------------------------------
def test_same_return_grades_differently_across_horizons():
    """A +0.8% move clears the 1d bar (0.5%) but NOT the 5d bar (~1.12%).

    Under the old horizon-blind rule this was a hit at every horizon — the
    single clearest expression of the bug.
    """
    assert ol._hit_rule("positive", 0.8, "1d") is True
    assert ol._hit_rule("positive", 0.8, "5d") is False
    assert ol._hit_rule("positive", 0.8, "20d") is False


def test_neutral_is_not_impossible_at_long_horizons():
    """A +1.5% move over 20 trading days is drift, not a real directional
    move — 'neutral' should hit. The old rule called this a miss, which is
    what crushed neutral-call hit rates at long horizons."""
    assert ol._hit_rule("neutral", 1.5, "20d") is True
    assert ol._hit_rule("neutral", 1.5, "1d") is False


def test_directional_call_is_not_free_at_long_horizons():
    """+0.6% over 20 trading days should NOT be a win for a bullish call."""
    assert ol._hit_rule("positive", 0.6, "20d") is False
    assert ol._hit_rule("positive", 0.6, "1d") is True


@pytest.mark.parametrize("horizon", ["1d", "5d", "20d"])
def test_direction_sign_still_matters_at_every_horizon(horizon):
    big = ol.hit_threshold_pct(horizon) * 3
    assert ol._hit_rule("positive", big, horizon) is True
    assert ol._hit_rule("positive", -big, horizon) is False
    assert ol._hit_rule("negative", -big, horizon) is True
    assert ol._hit_rule("negative", big, horizon) is False


@pytest.mark.parametrize("horizon", ["1d", "5d", "20d"])
def test_exact_threshold_is_a_hit_for_directional_and_a_miss_for_neutral(horizon):
    """Boundary: directional uses >=, neutral uses strict <. They must not
    overlap or both claim the exact-threshold move."""
    t = ol.hit_threshold_pct(horizon)
    assert ol._hit_rule("positive", t, horizon) is True
    assert ol._hit_rule("negative", -t, horizon) is True
    assert ol._hit_rule("neutral", t, horizon) is False
    assert ol._hit_rule("neutral", -t, horizon) is False


@pytest.mark.parametrize("horizon", ["1d", "5d", "20d"])
def test_mixed_and_none_never_count_as_hits(horizon):
    assert ol._hit_rule("mixed", 99.0, horizon) is False
    assert ol._hit_rule("positive", None, horizon) is False


def test_hit_rule_requires_an_explicit_horizon():
    """No default on purpose — a default is exactly how a new call site would
    silently reintroduce horizon-blind grading."""
    with pytest.raises(TypeError):
        ol._hit_rule("positive", 1.0)


# ---------------------------------------------------------------------------
# miss_fixtures must stay the exact inverse of the grading rule
# ---------------------------------------------------------------------------
def test_expected_direction_is_the_inverse_of_hit_rule():
    """A fixture's "right answer" has to be the direction that WOULD have
    hit at that horizon — otherwise the drafter is trained toward a target
    the grader disagrees with."""
    from app.services import miss_fixtures as mf

    for horizon in ol.HORIZONS_TD:
        t = ol.hit_threshold_pct(horizon)
        for ret in (-3 * t, -t, -t / 2, 0.0, t / 2, t, 3 * t):
            expected = mf._expected_direction(ret, horizon)
            assert ol._hit_rule(expected, ret, horizon) is True, (
                f"horizon={horizon} return={ret} expected={expected} "
                "is not actually a hit under _hit_rule"
            )


def test_expected_direction_tracks_the_horizon_not_a_fixed_band():
    from app.services import miss_fixtures as mf

    # +0.8%: a real up-move next-day, mere drift over a week.
    assert mf._expected_direction(0.8, "1d") == "positive"
    assert mf._expected_direction(0.8, "5d") == "neutral"
