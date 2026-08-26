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

from app.services.outcomes import outcome_ledger as ol


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
    from app.services.pathback import miss_fixtures as mf

    for horizon in ol.HORIZONS_TD:
        t = ol.hit_threshold_pct(horizon)
        for ret in (-3 * t, -t, -t / 2, 0.0, t / 2, t, 3 * t):
            expected = mf._expected_direction(ret, horizon)
            assert ol._hit_rule(expected, ret, horizon) is True, (
                f"horizon={horizon} return={ret} expected={expected} "
                "is not actually a hit under _hit_rule"
            )


def test_expected_direction_tracks_the_horizon_not_a_fixed_band():
    from app.services.pathback import miss_fixtures as mf

    # +0.8%: a real up-move next-day, mere drift over a week.
    assert mf._expected_direction(0.8, "1d") == "positive"
    assert mf._expected_direction(0.8, "5d") == "neutral"


# ---------------------------------------------------------------------------
# Per-ticker sigma scaling (2026-08-25)
#
# Second half of the same idea: sqrt(horizon) made the bar fair ACROSS
# HORIZONS, sigma makes it fair ACROSS STOCKS. Measured on 1621 real graded
# rows before this landed, a no-skill "always positive" guess scored 43.4% on
# top-third-volatility names vs 30.4% on bottom-third — a 13pp difficulty gap
# that was pure volatility, not skill.
# ---------------------------------------------------------------------------
def test_threshold_scales_with_the_stocks_own_volatility():
    """A 3%-sigma name must clear a bigger move than a 1%-sigma name for the
    same call at the same horizon. This is the whole point."""
    calm = ol.hit_threshold_pct("1d", 1.0)
    wild = ol.hit_threshold_pct("1d", 3.0)
    assert wild > calm
    # Linear in sigma — 3x the volatility, 3x the bar.
    assert wild == pytest.approx(3 * calm, rel=1e-6)


@pytest.mark.parametrize("horizon,td", [("1d", 1), ("5d", 5), ("20d", 20)])
def test_sigma_threshold_still_scales_as_sqrt_of_horizon(horizon, td):
    """Both scalings compose — losing either one reintroduces a known bug."""
    sigma = 2.0
    assert ol.hit_threshold_pct(horizon, sigma) == pytest.approx(
        ol.HIT_THRESHOLD_SIGMA_K * sigma * math.sqrt(td), abs=1e-4
    )


def test_missing_sigma_falls_back_to_the_flat_band():
    """Operationally normal (yfinance down, newly listed ticker, <20 bars) —
    must grade on the old band, not crash and not skip the row."""
    for horizon in ol.HORIZONS_TD:
        assert ol.hit_threshold_pct(horizon, None) == ol.hit_threshold_pct(horizon)


def test_sigma_is_clamped_at_both_ends():
    """Both guards exist against a garbage ESTIMATE, not against real vol:

    floor — an illiquid/stale-printing stock measures ~0 sigma, which without
            a floor produces a ~0 threshold and hands every directional call a
            free hit. That is the exact bug this rule exists to remove, so a
            zero-sigma stock must NOT end up easier than a normal one.
    cap   — an unadjusted split shows up as one enormous daily 'return' and
            would otherwise make a stock effectively unhittable.
    """
    floor_thr = ol.hit_threshold_pct("1d", ol.SIGMA_DAILY_PCT_FLOOR)
    assert ol.hit_threshold_pct("1d", 0.0) == floor_thr
    assert ol.hit_threshold_pct("1d", 0.01) == floor_thr

    cap_thr = ol.hit_threshold_pct("1d", ol.SIGMA_DAILY_PCT_CAP)
    assert ol.hit_threshold_pct("1d", 50.0) == cap_thr
    assert ol.hit_threshold_pct("1d", 999.0) == cap_thr


def test_k_stays_in_the_calibrated_band():
    """k is measured, not chosen — see hit_threshold_pct's docstring and
    scripts/calibrate_hit_threshold.py. The failure this guards against is
    someone 'fixing' a disappointing hit rate by moving k.

    The upper bound is the one that matters: at k=1.0 ("one sigma", the
    intuitive-but-wrong choice) a no-skill guess scores 83% on 'neutral' and
    ~8% on directional, which doesn't remove the free-hit problem, it just
    moves it to the other bucket.
    """
    assert 0.25 <= ol.HIT_THRESHOLD_SIGMA_K <= 0.40


def test_neutral_does_not_become_a_free_win():
    """The trap k guards against, stated as a property rather than a number.

    One threshold splits fixed probability mass between directional and
    neutral, so a bar high enough to stop crediting directional noise hands
    the same free win to 'neutral'. Under a normal random walk the neutral
    zone must stay well under half the distribution — at k=1.0 it is ~68%
    theoretically and measured 83% on real returns.
    """
    from statistics import NormalDist

    k = ol.HIT_THRESHOLD_SIGMA_K
    neutral_share = NormalDist().cdf(k) - NormalDist().cdf(-k)
    assert neutral_share < 0.40, (
        f"k={k} leaves {neutral_share:.0%} of a random walk inside the neutral "
        "band — 'neutral' is becoming the free bucket"
    )

    # NOT asserted here: that the three zones come out equal under this normal
    # model. They don't, and the gap is informative rather than a bug. Normal
    # theory says the levelling k is 0.431 (where each tail is exactly 1/3);
    # measured on 1621 real graded returns the levelling k is ~0.325. Real
    # daily returns are fat-tailed — more mass piled near zero than a normal
    # of the same sigma — so the neutral zone fills up faster than theory
    # predicts and the fair bar lands lower. k is calibrated against the
    # measured distribution, not this one; NormalDist is used above only as a
    # cheap dependency-free guard on the runaway direction.


@pytest.mark.parametrize("sigma", [0.8, 1.5, 2.5, 4.0])
@pytest.mark.parametrize("horizon", ["1d", "5d", "20d"])
def test_hit_rule_uses_the_sigma_it_is_given(horizon, sigma):
    t = ol.hit_threshold_pct(horizon, sigma)
    assert ol._hit_rule("positive", t, horizon, sigma) is True
    assert ol._hit_rule("positive", t * 0.99, horizon, sigma) is False
    assert ol._hit_rule("negative", -t, horizon, sigma) is True
    assert ol._hit_rule("neutral", t * 0.99, horizon, sigma) is True
    assert ol._hit_rule("neutral", t, horizon, sigma) is False


def test_same_return_grades_differently_for_calm_and_volatile_stocks():
    """The per-stock analogue of the cross-horizon test above: an identical
    +2% day is a real move for a quiet stock and noise for a wild one."""
    assert ol._hit_rule("positive", 1.0, "1d", 1.0) is True    # calm name
    assert ol._hit_rule("positive", 1.0, "1d", 5.0) is False   # wild name
    assert ol._hit_rule("neutral", 1.0, "1d", 5.0) is True


def test_expected_direction_inverts_hit_rule_under_sigma_too():
    """Same contract as the flat-band version, but the fixture must be built
    from the SAME sigma the grade used — otherwise miss_fixtures teaches the
    drafter a direction the grader scores as a miss."""
    from app.services.pathback import miss_fixtures as mf

    for horizon in ol.HORIZONS_TD:
        for sigma in (0.9, 2.0, 3.5):
            t = ol.hit_threshold_pct(horizon, sigma)
            for ret in (-3 * t, -t, -t / 2, 0.0, t / 2, t, 3 * t):
                expected = mf._expected_direction(ret, horizon, sigma)
                assert ol._hit_rule(expected, ret, horizon, sigma) is True, (
                    f"horizon={horizon} sigma={sigma} return={ret} "
                    f"expected={expected} is not a hit under _hit_rule"
                )


def test_expected_direction_with_wrong_sigma_can_disagree_with_the_grade():
    """Documents WHY sigma has to ride along on the row rather than being
    re-derived. Not asserting desired behaviour — asserting that the mismatch
    is real, so the plumbing in graded_misses() is never 'simplified' away."""
    from app.services.pathback import miss_fixtures as mf

    # Graded against a volatile name: +1.0% is inside the noise band, so the
    # direction that WOULD have hit is 'neutral'.
    assert mf._expected_direction(1.0, "1d", 4.0) == "neutral"
    # Re-derived without sigma it flips to 'positive' — a fixture built that
    # way would train toward an answer the grader calls wrong.
    assert mf._expected_direction(1.0, "1d") == "positive"
    assert ol._hit_rule("positive", 1.0, "1d", 4.0) is False


# ---------------------------------------------------------------------------
# _trailing_sigma_pct — the estimator, and its one non-negotiable property
# ---------------------------------------------------------------------------
def _series(prices: list[float]) -> tuple[dict[str, float], list[str]]:
    dates = [f"2026-01-{i + 1:02d}" for i in range(len(prices))]
    return dict(zip(dates, prices, strict=True)), dates


def test_trailing_sigma_never_looks_past_the_anchor():
    """THE property. If sigma could see the graded move, a stock that jumped
    would raise its own bar for having jumped — the threshold would chase the
    outcome and correct directional calls would be under-credited exactly
    when the model was right."""
    calm = [100.0 * (1.0 + 0.001 * (-1) ** i) for i in range(40)]
    history, dates = _series(calm + [200.0, 400.0])  # violent moves AFTER
    anchor = len(calm) - 1

    quiet = ol._trailing_sigma_pct(history, dates, anchor)
    assert quiet is not None
    assert quiet < 1.0, "anchor-window sigma should reflect the calm period"

    # Same series, anchored after the jumps — now the jumps are in-window.
    loud = ol._trailing_sigma_pct(history, dates, len(dates) - 1)
    assert loud > quiet * 5, "sanity: the jumps ARE huge when legitimately visible"


def test_trailing_sigma_returns_none_below_min_observations():
    """A newly listed ticker must produce None (-> flat fallback), never a
    wild estimate off three bars."""
    history, dates = _series([100.0 + i for i in range(5)])
    assert ol._trailing_sigma_pct(history, dates, 4) is None


def test_trailing_sigma_matches_stdev_of_daily_returns():
    import statistics as _stats

    prices = [100.0, 101.0, 99.5, 102.0, 100.5] * 6  # 30 bars
    history, dates = _series(prices)
    anchor = len(prices) - 1
    expected = _stats.stdev([
        (prices[i] - prices[i - 1]) / prices[i - 1] * 100.0
        for i in range(max(1, anchor - ol.SIGMA_LOOKBACK_TD + 1), anchor + 1)
    ])
    got = ol._trailing_sigma_pct(history, dates, anchor)
    assert got == pytest.approx(expected, rel=1e-9)
