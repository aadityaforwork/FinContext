"""
Prompt-version monitor — Phase 3 (online, can revert)
=========================================================
Daily idempotent job (see app/routers/prompt_monitor.py's admin-token
endpoint, same shape as /api/outcomes/compute-daily) that compares
deterministic metrics for the currently-live version of a Langfuse-managed
prompt against the version that was live before it, and reverts the
`production` label back to that previous version if the live version has
degraded past both a sample-size and an effect-size threshold.

NON-NEGOTIABLE, enforced by this module's own design (not just convention):
  - This module NEVER promotes. It never calls `create_prompt` and never
    sets a label to a version that wasn't already, at some point, the live
    `production` version. The only Langfuse write it can ever make is
    `update_prompt(name, version=<previous live version>,
    new_labels=["production"])` — a revert, not a promotion. Forward promotion
    (relabeling a `candidate` to `production`) is a human action, always —
    see AGENTS.md.
  - Every component degrades to a no-op. Metric rows come from
    outcome_ledger.call_metrics_rows(), which never raises and returns []
    on any failure — that alone makes `evaluate()` a no-op (insufficient
    sample) with zero special-casing needed here. The revert write itself
    is wrapped in its own try/except. evaluate() itself never raises into
    its caller (the admin endpoint) — any unexpected failure is caught and
    reported as an "error" action, never propagated.
  - Every decision is logged, including no-ops, with the reason — see the
    `reason` field on every returned dict below. The admin endpoint returns
    this same dict as the response body, so "what did the monitor decide
    today" is answerable either from logs or from the cron's own response.

HOW "current" AND "previous" VERSION ARE DETERMINED: this module does NOT
track its own separate state table for "what was live before" — it derives
it from prompt_call_log history itself (outcome_ledger.call_metrics_rows),
ordered newest-first: the most recent distinct `prompt_version` among rows
with prompt_source == "langfuse" is "current"; the next distinct version
back is "previous". This means the monitor's own view of history IS the
call log — no separate state to keep in sync, and it's naturally correct
after a revert (once reverted, "current" becomes the old "previous" again,
which by construction wasn't degraded, so a second consecutive run is a
no-op rather than reverting again — this is what makes the job idempotent).

Public API:
    MONITORED_PROMPTS: tuple[str, ...]
    evaluate(prompt_name, days=LOOKBACK_DAYS) -> dict  (never raises)
"""

from __future__ import annotations

import logging

from app.services import langfuse_client, outcome_ledger

logger = logging.getLogger(__name__)

# Only the two prompts that are actually Langfuse-managed and produce judged
# predictions — same scope decision as prompt_registry.py (path-back leg
# 3b). Extend this the same way that module says to extend its own scope:
# once a new prompt has real logged/judged volume, not before.
MONITORED_PROMPTS = ("portfolio.tomorrow_watch", "portfolio.news_feed_annotation")

# How far back to look for call-log rows when deriving current/previous
# version history. 30 days matches track_record.py's LOOKBACK_DAYS-adjacent
# choices elsewhere in the path-back system — long enough to accumulate
# MIN_SAMPLE_SIZE calls for a low-traffic prompt, short enough that a
# version from months ago can't quietly become "previous" again.
LOOKBACK_DAYS = 30

# ---------------------------------------------------------------------------
# Deterministic metrics compared between the live version and the
# previously-live version. All five are plain aggregates over
# prompt_call_log rows (outcome_ledger.call_metrics_rows) — no LLM judges
# anything.
#   - data_gaps_rate: fraction of calls whose response listed >=1 data_gaps
#     entry. Rising = the prompt is increasingly unable to ground its
#     answer in CONTEXT (AGENTS.md rule 1) — a real quality regression.
#   - schema_validation_failure_rate: fraction of calls whose JSON failed
#     to parse (generate_grounded_json's own parse_error flag). Rising =
#     the model is drifting off the required output schema — usually a
#     prompt edit that confused the contract. The only metric that can be
#     computed for calls with ZERO downstream ai_predictions rows, which is
#     exactly why prompt_call_log exists as its own table (see
#     outcome_ledger.log_call_metrics' docstring).
#   - confidence_low_share: fraction of calls (that reported a confidence
#     at all — not every judged prompt's schema has that field, e.g.
#     news_feed_annotation doesn't) whose self-reported confidence was
#     "low". Rising = the model trusts its own answers less.
#   - tokens_per_call: mean(tokens_in + tokens_out). A sharp rise usually
#     means a prompt edit bloated CONTEXT or asked for more verbose output
#     — a cost regression even when quality doesn't move.
#   - p95_latency_ms: 95th-percentile call duration. A rise means a prompt
#     edit made the model "think" more (longer completions) — a
#     user-facing latency regression on these SSE-streamed endpoints.
# ---------------------------------------------------------------------------
METRICS = (
    "data_gaps_rate",
    "schema_validation_failure_rate",
    "confidence_low_share",
    "tokens_per_call",
    "p95_latency_ms",
)

# Cold-start rule: a version needs at least this many logged calls before
# its metrics are trusted enough to compare AT ALL. Below this for either
# side, log "insufficient sample" and take no action. Same "~10 real
# observations" intuition as track_record.py's SHRINKAGE_STRENGTH, applied
# as a hard floor rather than a blend here — this module's action (an
# automatic revert of a live prompt) is higher-stakes than shrinking a
# conviction score, so it's a gate, not a smooth blend.
MIN_SAMPLE_SIZE = 20

# Minimum effect size, per metric, required to call a degradation "real"
# rather than sampling noise. Rate metrics (0-1 scale) use an absolute
# percentage-point jump; tokens/latency use a relative (%) jump since their
# raw scale varies a lot by prompt/schema. Same margin-over-noise-floor
# reasoning as prompt_gate.py's CASE_REGRESSION_BLOCK/MIN_OVERALL_IMPROVEMENT
# (see that module's docstring) — these should be re-validated the same way
# (compare a version's own history against itself) rather than trusted
# blind once there's enough call volume to do that.
MIN_EFFECT = {
    "data_gaps_rate": 0.20,                   # +20 percentage points
    "schema_validation_failure_rate": 0.15,   # +15pp — even a small rise here is a real break
    "confidence_low_share": 0.20,             # +20pp
    "tokens_per_call": 0.30,                  # +30% relative
    "p95_latency_ms": 0.40,                   # +40% relative
}

# Which direction counts as "worse" for each metric — all five are
# "higher is worse" today, but kept as an explicit table (not a hardcoded
# assumption in the comparison code) so a future metric with the opposite
# polarity doesn't require touching the comparison logic itself.
HIGHER_IS_WORSE = {m: True for m in METRICS}

# Metrics on a 0-1 rate scale compare via an absolute (percentage-point)
# effect; everything else (tokens, latency) compares via a relative effect
# since their raw scale varies a lot by prompt/schema — see MIN_EFFECT.
_RATE_METRICS = {"data_gaps_rate", "schema_validation_failure_rate", "confidence_low_share"}


def _percentile(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    idx = min(len(sorted_vals) - 1, max(0, round(p * (len(sorted_vals) - 1))))
    return sorted_vals[idx]


def _aggregate(rows: list[dict]) -> dict:
    """Compute the five METRICS (plus sample size `n`) over a list of
    prompt_call_log rows for a single version. A metric whose inputs are
    entirely absent (e.g. confidence_low_share for a prompt whose schema
    never reports confidence) comes back None — "not applicable", handled
    as such by _compare_metric below, never treated as a 0% rate."""
    n = len(rows)
    if n == 0:
        return {"n": 0, **{m: None for m in METRICS}}

    gaps = sum(1 for r in rows if (r.get("data_gaps_count") or 0) > 0)
    fails = sum(1 for r in rows if r.get("parse_error"))
    conf_rows = [r for r in rows if r.get("confidence") is not None]
    low_conf = sum(1 for r in conf_rows if r.get("confidence") == "low")
    token_totals = [
        (r.get("tokens_in") or 0) + (r.get("tokens_out") or 0)
        for r in rows
        if r.get("tokens_in") is not None or r.get("tokens_out") is not None
    ]
    durations = sorted(r["duration_ms"] for r in rows if r.get("duration_ms") is not None)

    return {
        "n": n,
        "data_gaps_rate": round(gaps / n, 3),
        "schema_validation_failure_rate": round(fails / n, 3),
        "confidence_low_share": round(low_conf / len(conf_rows), 3) if conf_rows else None,
        "tokens_per_call": round(sum(token_totals) / len(token_totals), 1) if token_totals else None,
        "p95_latency_ms": _percentile(durations, 0.95),
    }


def _compare_metric(name: str, current: float | None, previous: float | None) -> dict:
    """One metric's before/after/effect/degraded verdict. `effect` and
    `degraded` are None/False whenever either side lacks the metric (not
    applicable to this prompt's schema, or genuinely zero calls) — a
    missing metric is never treated as a degradation."""
    if current is None or previous is None:
        return {"current": current, "previous": previous, "effect": None, "degraded": False}

    if name in _RATE_METRICS:
        effect = round(current - previous, 3)
    else:
        effect = round((current - previous) / previous, 3) if previous else None

    degraded = (
        effect is not None
        and HIGHER_IS_WORSE[name]
        and effect >= MIN_EFFECT[name]
    )
    return {"current": current, "previous": previous, "effect": effect, "degraded": degraded}


def _distinct_versions_newest_first(rows: list[dict]) -> list[int]:
    """Real (non-None) Langfuse version numbers, in order of first
    appearance in `rows` (which call_metrics_rows already returns
    newest-first), deduped."""
    seen: list[int] = []
    for r in rows:
        v = r.get("prompt_version")
        if v is not None and v not in seen:
            seen.append(v)
    return seen


def _revert_production_label(prompt_name: str, previous_version: int) -> tuple[bool, str]:
    """The ONLY Langfuse write this whole feature is allowed to make: point
    `production` back at a version that was already live before. Never
    raises — returns (False, reason) on any failure (no client configured,
    SDK error, etc.) so evaluate() can report an honest outcome even when
    the write itself couldn't happen.

    NOTE: the SDK method is `update_prompt` (not `update_prompt_labels` —
    that name doesn't exist on langfuse-python's `Langfuse` client; found
    2026-08-13 while wiring prompt_drafter.py's identical write path. The
    original code here called the non-existent method, so every real revert
    attempt was silently swallowed by this function's own try/except and
    reported as "revert_failed" — never actually wrote the label. Confirmed
    against the installed langfuse 4.14.3 client via
    `inspect.signature(Langfuse.update_prompt)`."""
    client = langfuse_client.get_client()
    if client is None:
        return False, "Langfuse not configured — cannot write the revert label"
    try:
        client.update_prompt(name=prompt_name, version=previous_version, new_labels=["production"])
        return True, "reverted"
    except Exception as e:
        logger.exception("prompt_monitor: revert label write failed for %s v%s", prompt_name, previous_version)
        return False, f"revert label write failed: {e}"


def evaluate(prompt_name: str, days: int = LOOKBACK_DAYS) -> dict:
    """Run the daily comparison for one prompt. Never raises — any
    unexpected failure is caught and reported as action="error" rather
    than propagating (this is called from an admin-token endpoint that
    must return a clean response either way).

    Returns a dict always containing at least {"prompt_name", "action",
    "reason"}; `action` is one of:
      "insufficient_sample" — cold-start rule; no comparison was made.
      "no_action"           — compared, no metric degraded past threshold.
      "reverted"            — compared, degradation found, label reverted.
      "revert_failed"       — degradation found, but the Langfuse write
                               itself failed (see `reason`).
      "error"               — evaluate() caught an unexpected exception.
    """
    try:
        rows = outcome_ledger.call_metrics_rows(prompt_name, days=days)
        langfuse_rows = [r for r in rows if r.get("prompt_source") == "langfuse"]
        versions = _distinct_versions_newest_first(langfuse_rows)

        if len(versions) < 2:
            reason = (
                "no Langfuse-managed call history yet" if not versions
                else f"only one version (v{versions[0]}) seen in the last {days}d — nothing to compare against"
            )
            logger.info("prompt_monitor[%s]: insufficient_sample — %s", prompt_name, reason)
            return {"prompt_name": prompt_name, "action": "insufficient_sample", "reason": reason}

        current_version, previous_version = versions[0], versions[1]
        current_rows = [r for r in langfuse_rows if r["prompt_version"] == current_version]
        previous_rows = [r for r in langfuse_rows if r["prompt_version"] == previous_version]

        if len(current_rows) < MIN_SAMPLE_SIZE or len(previous_rows) < MIN_SAMPLE_SIZE:
            reason = (
                f"sample too small: current v{current_version} n={len(current_rows)}, "
                f"previous v{previous_version} n={len(previous_rows)} (need >= {MIN_SAMPLE_SIZE} each)"
            )
            logger.info("prompt_monitor[%s]: insufficient_sample — %s", prompt_name, reason)
            return {
                "prompt_name": prompt_name, "action": "insufficient_sample", "reason": reason,
                "current_version": current_version, "previous_version": previous_version,
            }

        current_agg = _aggregate(current_rows)
        previous_agg = _aggregate(previous_rows)
        comparison = {m: _compare_metric(m, current_agg[m], previous_agg[m]) for m in METRICS}
        degraded_metrics = [m for m, c in comparison.items() if c["degraded"]]

        if not degraded_metrics:
            reason = f"no metric degraded past threshold (v{current_version} vs v{previous_version})"
            logger.info("prompt_monitor[%s]: no_action — %s | %s", prompt_name, reason, comparison)
            return {
                "prompt_name": prompt_name, "action": "no_action", "reason": reason,
                "current_version": current_version, "previous_version": previous_version,
                "comparison": comparison,
            }

        reason = (
            f"degraded on {', '.join(degraded_metrics)} — v{current_version} vs previously-live "
            f"v{previous_version}: " + "; ".join(
                f"{m}: {comparison[m]['previous']} -> {comparison[m]['current']} "
                f"({comparison[m]['effect']:+})"
                for m in degraded_metrics
            )
        )
        reverted, write_result = _revert_production_label(prompt_name, previous_version)
        action = "reverted" if reverted else "revert_failed"
        # This is the "notify" step — logger.error reaches Sentry Logs for
        # this deployment (see CLAUDE.md "Sentry" section: enable_logs is on
        # and a stdlib logger.error() is confirmed to land there), so a
        # revert (or a failed attempt at one) is visible without adding a
        # second, bespoke notification channel just for this feature.
        logger.error(
            "prompt_monitor[%s]: %s — %s | write_result=%s",
            prompt_name, action, reason, write_result,
        )
        return {
            "prompt_name": prompt_name, "action": action, "reason": reason,
            "current_version": current_version, "previous_version": previous_version,
            "comparison": comparison, "degraded_metrics": degraded_metrics,
            "write_result": write_result,
        }
    except Exception as e:
        logger.exception("prompt_monitor[%s]: evaluate() failed unexpectedly", prompt_name)
        return {"prompt_name": prompt_name, "action": "error", "reason": str(e)}
