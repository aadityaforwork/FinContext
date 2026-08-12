"""
Track Record — calibration signal for the ensemble (path-back, leg 1)
=======================================================================
This is the first closed loop in the Record -> Judge -> Path-back chain
(see the "Self-Iterating System" design doc in Notion). Record is
outcome_ledger.log_predictions(); Judge is outcome_ledger.compute_pending_
outcomes() (daily cron, real yfinance price moves). This module is the
Path back: it turns those judged outcomes into a conviction multiplier
applied on top of signal_ensemble's existing weighted vote, so a
catalyst/source combo with a genuinely bad track record gets discounted
(and, via signal_ensemble.MIN_CONVICTION_FOR_USER, progressively hidden)
and a well-calibrated one gets a modest boost.

Why this signal first ("fastest and most specific"):
  - Fastest: the 1d horizon is the quickest judged signal the ledger
    produces — a prediction made today is scoreable tomorrow. 5d/20d carry
    more information eventually but lag weeks behind, too slow to be the
    first feedback signal.
  - Most specific: (source, catalyst_type) is the finest breakdown we can
    trust for sample size today. impact_level- and ticker-level
    calibration are the natural next increments once volume supports them
    — deliberately not done here yet (see Notion doc's "other things").

NAMED TRADE-OFF, not a free lunch: grading at 1d optimizes for loop speed,
not signal fidelity. A "Tomorrow" watch item is inherently a next-session
call so 1d is the right horizon for it — but if a future prediction source
is really a 5d/20d thesis, calibrating its trust on next-day price action
would be tuning against the wrong ground truth. Revisit per-source horizon
choice before extending calibration to a new prediction source; don't
assume 1d is universally correct just because it's what's wired up today.

WHY SHRINKAGE, NOT A HARD SAMPLE-SIZE CUTOFF: an earlier version of this
module picked the finest (source, catalyst_type)/source/global tier with
>= MIN_SAMPLE observations and used its raw hit-rate, ignoring parent tiers
entirely below that cliff. Two problems with that: (1) at n=10, three hits
out of ten (a perfectly ordinary outcome for a true 50%-skill segment) was
taken at face value and produced a real discount off unlucky noise; (2) the
factor could jump discontinuously the moment a segment crossed the n=10
line, rather than earning trust gradually. Instead, each tier's estimate is
a weighted blend of its own observed hit-rate and its parent tier's
estimate (global's parent is the 50% coin-flip prior), weighted by
SHRINKAGE_STRENGTH "pseudo-observations" of the parent. A segment with zero
data inherits its parent's estimate exactly (factor 1.0 when every tier is
empty — same behavior the old cold-start case gave, just as the zero-data
limit of one continuous formula instead of a special-cased branch). A
segment with a lot of data converges to its own observed rate. This is
standard empirical-Bayes/hierarchical shrinkage — see e.g. James-Stein or
Beta-Binomial hierarchical models for the general technique.

AUDIT TRAIL: signal_ensemble's conviction now depends on history, so the
same call can score differently on different days for reasons that live in
Supabase, not in this file. calibrate() therefore returns every input that
went into the factor (pair/source/global n + hits, the blended hit-rate)
so callers can persist it — see calibration_factor's docstring and
portfolio_intelligence.py's _log_tomorrow_predictions/_log_news_feed_
predictions, which write this into ai_predictions.metadata (already a
jsonb column — no migration needed) so any past call's conviction is
reconstructable after the fact.

Cold-start / no-data safe: with zero scored outcomes anywhere,
calibration_factor() returns factor == 1.0 (see zero-data limit above),
i.e. byte-identical to pre-path-back behavior. Never raises; any Supabase/
query failure degrades to 1.0 rather than distorting conviction on bad
data.

Public API:
    calibrate(ensemble, source, catalyst_type) -> ensemble dict, with
        conviction recalibrated + calibration_* audit fields attached.
    calibration_factor(source, catalyst_type) -> {factor, hit_rate_pct,
        pair_n, pair_hits, source_n, source_hits, global_n, global_hits}
"""

from __future__ import annotations

import logging
from collections import defaultdict

from app.services import outcome_ledger
from app.services.cache import make_named_cache

logger = logging.getLogger(__name__)

HORIZON = "1d"           # fastest judged signal — see module docstring
LOOKBACK_DAYS = 90        # match outcome_ledger's own bounded query window

# "Pseudo-observation" strength of the parent tier's estimate when blending
# it with a tier's own (possibly thin) data — see SHRINKAGE docstring above.
# 10 was the old hard MIN_SAMPLE cutoff; reused here as the shrinkage
# strength so a segment needs "about 10 real observations" to outweigh its
# parent, same intuition, just applied smoothly instead of as a cliff.
SHRINKAGE_STRENGTH = 10.0

# The ultimate prior at the top of the hierarchy — no data anywhere means
# "coin flip", i.e. no calibration effect.
GLOBAL_PRIOR = 0.5

# Asymmetric on purpose: a proven-bad segment should be discounted harder
# than a proven-good segment gets rewarded — matches signal_ensemble's own
# "markets are never certain" ceiling philosophy (conviction capped at 95).
FACTOR_FLOOR = 0.70
FACTOR_CEIL = 1.15

_cache = make_named_cache("track_record", maxsize=1)
_CACHE_KEY = "segments"


def _compute_segments() -> dict:
    """{"pair": {(source, catalyst_type): (n, hits)}, "source": {source: (n, hits)}, "global": (n, hits)}"""
    rows = outcome_ledger.scored_rows(horizon=HORIZON, days=LOOKBACK_DAYS)

    pair: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    by_source: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    glob = [0, 0]

    for r in rows:
        hit = r.get("hit")
        if hit is None:
            continue
        source = r.get("source") or "unknown"
        catalyst = r.get("catalyst_type") or "unknown"

        p = pair[(source, catalyst)]
        p[0] += 1
        p[1] += 1 if hit else 0

        s = by_source[source]
        s[0] += 1
        s[1] += 1 if hit else 0

        glob[0] += 1
        glob[1] += 1 if hit else 0

    return {"pair": dict(pair), "source": dict(by_source), "global": tuple(glob)}


def _load_segments() -> dict:
    cached = _cache.get(_CACHE_KEY)
    if cached is not None:
        return cached
    data = _compute_segments()
    _cache[_CACHE_KEY] = data
    return data


def _shrink(n: int, hits: int, prior_rate: float) -> float:
    """Blend a tier's own hit-rate with its parent's estimate, weighted by
    SHRINKAGE_STRENGTH pseudo-observations of the parent. n=0 -> prior_rate
    exactly; n >> SHRINKAGE_STRENGTH -> converges to hits/n."""
    return (hits + SHRINKAGE_STRENGTH * prior_rate) / (n + SHRINKAGE_STRENGTH)


def _factor_from_rate(hit_rate: float) -> float:
    """Linear, centered on a coin-flip: 50% hit rate -> 1.0 (no change),
    0% -> FACTOR_FLOOR, 100% -> FACTOR_CEIL."""
    if hit_rate >= 0.5:
        factor = 1.0 + (hit_rate - 0.5) / 0.5 * (FACTOR_CEIL - 1.0)
    else:
        factor = 1.0 - (0.5 - hit_rate) / 0.5 * (1.0 - FACTOR_FLOOR)
    return round(factor, 3)


_COLD_START: dict = {
    "factor": 1.0, "hit_rate_pct": None,
    "pair_n": 0, "pair_hits": 0, "source_n": 0, "source_hits": 0,
    "global_n": 0, "global_hits": 0,
}


def calibration_factor(source: str, catalyst_type: str | None) -> dict:
    """Hierarchical-shrinkage hit-rate estimate for (source, catalyst_type),
    turned into a conviction multiplier.

    Returns every count that fed the estimate — pair/source/global n + hits
    — plus the final blended `hit_rate_pct` and `factor`, so a caller can
    persist the whole thing for later audit (see module docstring).
    Never raises; degrades to the all-zero cold-start dict (factor 1.0) on
    any failure.
    """
    try:
        segments = _load_segments()
    except Exception:
        logger.exception("track_record: segment load failed, no calibration applied")
        return dict(_COLD_START)

    catalyst_key = catalyst_type or "unknown"
    global_n, global_hits = segments["global"] or (0, 0)
    source_n, source_hits = segments["source"].get(source, (0, 0))
    pair_n, pair_hits = segments["pair"].get((source, catalyst_key), (0, 0))

    global_rate = _shrink(global_n, global_hits, GLOBAL_PRIOR)
    source_rate = _shrink(source_n, source_hits, global_rate)
    pair_rate = _shrink(pair_n, pair_hits, source_rate)

    return {
        "factor": _factor_from_rate(pair_rate),
        "hit_rate_pct": round(100 * pair_rate, 1),
        "pair_n": pair_n, "pair_hits": pair_hits,
        "source_n": source_n, "source_hits": source_hits,
        "global_n": global_n, "global_hits": global_hits,
    }


def calibrate(ensemble: dict, source: str, catalyst_type: str | None) -> dict:
    """Apply the track-record multiplier to an ensemble's conviction score.

    Only touches `conviction` — never overrides `consensus_direction`; the
    track record says how reliable this segment's calls have been, not
    which way the market will move. Returns a new dict (doesn't mutate the
    input) with `raw_conviction` preserved and `calibration_*` audit fields
    added — callers are expected to persist these (see module docstring)
    so any past prediction's conviction is reconstructable later.

    Best-effort — never raises. On any failure, returns `ensemble` with
    raw_conviction == conviction (no-op).
    """
    try:
        cal = calibration_factor(source, catalyst_type)
    except Exception:
        logger.exception("track_record.calibrate failed, returning ensemble unmodified")
        cal = dict(_COLD_START)

    raw = ensemble.get("conviction", 50)
    calibrated = max(0, min(95, round(raw * cal["factor"])))

    out = dict(ensemble)
    out["raw_conviction"] = raw
    out["conviction"] = calibrated
    out["calibration_factor"] = cal["factor"]
    out["calibration_hit_rate_pct"] = cal["hit_rate_pct"]
    out["calibration_pair_n"] = cal["pair_n"]
    out["calibration_pair_hits"] = cal["pair_hits"]
    out["calibration_source_n"] = cal["source_n"]
    out["calibration_source_hits"] = cal["source_hits"]
    out["calibration_global_n"] = cal["global_n"]
    out["calibration_global_hits"] = cal["global_hits"]
    return out
