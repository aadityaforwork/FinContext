"""
Signal Ensemble
===============
Combines independent signals (news direction, technical state, sector flow,
FII/DII flow) into a single conviction-weighted directional call.

Philosophy: SELECTIVITY > COVERAGE. The system should emit fewer, sharper
predictions — only when multiple independent signals agree. Conflicting
signals collapse to neutral. Predictions below the conviction threshold are
dropped from the user-facing output but still logged to the outcome ledger
so we can backtest the rule against what would have happened if we'd kept
them.

A 65% conviction call backed by news + technicals agreeing is far more
defensible than a 90% LLM "POSITIVE" with no corroboration. We trade quantity
for honest uncertainty.

Public API:
    compute_ensemble(news_direction, technicals, sector_change, flows)
        → {consensus_direction, conviction, breakdown, agreeing, conflicting}
    MIN_CONVICTION_FOR_USER  — items below this get dropped from UI
"""

from __future__ import annotations

# Predictions with conviction below this are dropped from user-facing output.
# They still get logged to the ledger for calibration analysis.
MIN_CONVICTION_FOR_USER = 50

# Per-signal weights for the ensemble vote. News is the catalyst (highest);
# technicals confirm/contradict; sector + flow are macro context modifiers.
SIGNAL_WEIGHTS = {
    "news":   25,
    "tech":   20,
    "sector": 15,
    "flow":   10,
}

# Bands beyond which a sector return / flow / score is considered directional.
SECTOR_DIRECTIONAL_PCT = 1.0     # |sector return| ≥ 1.0% → directional
FLOW_DIRECTIONAL_CR    = 1000.0  # |fii_net + dii_net| ≥ 1000cr → directional
SCORE_DIRECTIONAL      = 5       # |weighted score| ≥ 5 → directional consensus


def _technical_direction(tech: dict | None) -> str | None:
    """Infer overall technical direction from RSI + momentum + SMA state.
    Returns 'positive' | 'negative' | 'neutral' | None (no data).

    Composite read — no single technical wins; we average a few.
    """
    if not tech:
        return None

    score = 0.0
    n = 0

    # Momentum state — strongest single technical
    ms = tech.get("momentum_state")
    if ms == "extending_up":     score += 1.0; n += 1
    elif ms == "extending_down": score -= 1.0; n += 1
    elif ms == "reversing_up":   score += 0.5; n += 1
    elif ms == "reversing_down": score -= 0.5; n += 1

    # Trend regime — above/below 50d MA
    sma = tech.get("sma_state")
    if sma == "above_sma50":   score += 0.5; n += 1
    elif sma == "below_sma50": score -= 0.5; n += 1

    # RSI extremes are CONTRARIAN — oversold = bounce setup, overbought = pause
    rsi = tech.get("rsi_zone")
    if rsi == "oversold":     score += 0.5; n += 1
    elif rsi == "overbought": score -= 0.5; n += 1
    elif rsi == "weak":       score -= 0.25; n += 1
    elif rsi == "strong":     score += 0.25; n += 1

    if n == 0:
        return None
    avg = score / n
    if avg > 0.3:  return "positive"
    if avg < -0.3: return "negative"
    return "neutral"


def _sector_direction(sector_change_pct: float | None) -> str | None:
    if sector_change_pct is None:
        return None
    if sector_change_pct >  SECTOR_DIRECTIONAL_PCT: return "positive"
    if sector_change_pct < -SECTOR_DIRECTIONAL_PCT: return "negative"
    return "neutral"


def _flow_direction(flows: dict | None) -> str | None:
    """Direction from FII + DII combined net flow. Strong combined buying = +."""
    if not flows:
        return None
    fii = flows.get("fii_net_cr")
    dii = flows.get("dii_net_cr")
    if fii is None and dii is None:
        return None
    combined = (fii or 0) + (dii or 0)
    if combined >  FLOW_DIRECTIONAL_CR: return "positive"
    if combined < -FLOW_DIRECTIONAL_CR: return "negative"
    return "neutral"


def _dir_to_int(d: str | None) -> int:
    if d == "positive": return 1
    if d == "negative": return -1
    return 0


def compute_ensemble(
    news_direction: str | None,
    technicals: dict | None = None,
    sector_change_pct: float | None = None,
    flows: dict | None = None,
) -> dict:
    """Combine the four signals into a consensus + conviction score.

    Returns:
      {
        consensus_direction: 'positive' | 'negative' | 'neutral',
        conviction:          int 0-95   (capped — markets are never certain),
        breakdown:           {news, tech, sector, flow} → direction (or None),
        agreeing_signals:    int (count of signals matching consensus),
        conflicting_signals: int (count of signals opposing consensus),
        signal_count:        int (signals that had data at all),
      }
    """
    breakdown: dict[str, str | None] = {
        "news":   news_direction,
        "tech":   _technical_direction(technicals),
        "sector": _sector_direction(sector_change_pct),
        "flow":   _flow_direction(flows),
    }

    # Weighted score: each signal contributes weight * direction_int.
    # max_weight is the total weight of signals that actually had data —
    # used to normalize conviction so absence of data isn't penalized.
    score = 0
    max_weight = 0
    for k, d in breakdown.items():
        w = SIGNAL_WEIGHTS[k]
        if d is None:
            continue
        max_weight += w
        score += _dir_to_int(d) * w

    # Consensus from sign of score with a small dead band.
    if score >  SCORE_DIRECTIONAL:
        consensus = "positive"
    elif score < -SCORE_DIRECTIONAL:
        consensus = "negative"
    else:
        consensus = "neutral"

    # Count agreeing / conflicting signals relative to consensus.
    agreeing = sum(
        1 for d in breakdown.values()
        if d and _dir_to_int(d) == _dir_to_int(consensus) and d != "neutral"
    )
    conflicting = sum(
        1 for d in breakdown.values()
        if d and consensus != "neutral" and _dir_to_int(d) == -_dir_to_int(consensus)
    )
    # If consensus is neutral, "conflicting" means any directional signal at all
    # (because a directional signal disagrees with our neutral call).
    if consensus == "neutral":
        conflicting = sum(1 for d in breakdown.values() if d in ("positive", "negative"))

    # Conviction
    # Base 50 (no signal). Scale to 95 based on |score| / max_weight.
    if max_weight > 0:
        # |score| is dampened if signals disagree; divide by max gives 0–1.
        ratio = abs(score) / max_weight
        conviction = 50 + ratio * 45
    else:
        conviction = 50

    # Penalty for any conflict — even one opposing signal kills high conviction.
    conviction -= conflicting * 8

    # If news (the catalyst) is missing or neutral, cap conviction lower —
    # technicals alone shouldn't carry a high-conviction call.
    if breakdown["news"] in (None, "neutral"):
        conviction = min(conviction, 65)

    # Hard ceiling — markets are never 95+% predictable. Anyone claiming higher
    # is overfitting. Floor at 0 in case heavy conflict pushed below.
    conviction = max(0, min(95, round(conviction)))

    return {
        "consensus_direction": consensus,
        "conviction": conviction,
        "breakdown": breakdown,
        "agreeing_signals": agreeing,
        "conflicting_signals": conflicting,
        "signal_count": sum(1 for d in breakdown.values() if d is not None),
    }


def short_explanation(ensemble: dict) -> str:
    """Human-readable one-liner for the UI tooltip / debug.
    Example: 'news + tech agree (positive); sector neutral; flow disagrees'.
    """
    if not ensemble:
        return ""
    b = ensemble.get("breakdown") or {}
    consensus = ensemble.get("consensus_direction", "neutral")
    parts = []
    for k, d in b.items():
        if d is None:
            continue
        if d == consensus and d != "neutral":
            parts.append(f"{k} agrees")
        elif d == "neutral":
            parts.append(f"{k} neutral")
        else:
            parts.append(f"{k} disagrees ({d})")
    return "; ".join(parts) if parts else "no signal data"
