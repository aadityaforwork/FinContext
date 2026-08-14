"""
Accuracy monitor — path-back leg 3c: market-accuracy drift alert
====================================================================
Daily idempotent job (see app/routers/accuracy_monitor.py's admin-token
endpoint, same shape as /api/outcomes/compute-daily and
/api/prompt-monitor/run-daily) that compares a segment's recent
market-graded hit rate against its own trailing baseline and, if it's
dropped past both a sample-size and an effect-size threshold, pushes a
Telegram alert to the operator.

WHY THIS EXISTS: the market already grades every prediction correctly
(outcome_ledger.compute_pending_outcomes(), daily). What's missing is a job
connecting "this segment's hit rate just dropped" to "someone should look
at the prompt" — today the only way anyone finds that out is by opening the
Accuracy page and noticing.

HOW THIS DIFFERS FROM prompt_monitor.py (leg 3b, Phase 3): that module
compares LLM-CALL-level deterministic metrics (data gaps, schema-validation
failures, tokens, latency — from prompt_call_log) between two prompt
VERSIONS, and MAY auto-revert the Langfuse `production` label. This module
compares real MARKET-GRADED accuracy (hit rate, from prediction_outcomes)
for a SEGMENT over time, and only ever ALERTS. It never reverts, promotes,
or writes anything to Langfuse — a hit-rate drop can come from a genuine
market regime change just as easily as a bad prompt edit, and telling those
apart is a human judgment call, not a deterministic one. That's the whole
reason this is a notification, not an action.

SEGMENTS = `source` (tomorrow_per_holding | news_feed), not the finer
(source, catalyst_type) pair track_record.py calibrates on. Deliberate:
`source` maps 1:1 onto exactly one Langfuse-managed prompt (SOURCE_TO_PROMPT
below), so an alert can always say "open THIS prompt" — and staying at the
source grain keeps the recent-window sample size viable, where splitting
further by catalyst_type would rarely clear MIN_SAMPLE_SIZE within
RECENT_WINDOW_DAYS.

NON-NEGOTIABLE, enforced by this module's own design (not just convention):
  - Never writes anywhere except its own audit-log table
    (outcome_ledger.log_accuracy_alert) and a Telegram message. No Langfuse
    client is even imported here.
  - Every component degrades to a no-op. Rows come from
    outcome_ledger.scored_rows(), which never raises and returns [] on any
    failure — that alone makes evaluate() a no-op (insufficient sample).
    The Telegram send and the audit-log write are each best-effort.
    evaluate() itself never raises into its caller (the admin endpoint) —
    any unexpected failure is caught and reported as an "error" action.
  - Every decision is logged, including no-ops, with the reason — see the
    `reason` field on every returned dict below.

Public API:
    SOURCE_TO_PROMPT: dict[str, str]
    evaluate(source, days=LOOKBACK_DAYS) -> dict  (never raises)
"""

from __future__ import annotations

import html
import logging
from datetime import datetime, timedelta, timezone

from app.services import outcome_ledger, telegram_bot

logger = logging.getLogger(__name__)

# `source` -> the Langfuse-managed prompt responsible for that source's
# calls. 1:1 by construction — see portfolio_intelligence.py's
# _tomorrow_prompt_meta / _news_prompt_meta, which stamp exactly these
# `source` values onto every logged prediction. Same scope decision as
# prompt_registry.py / prompt_monitor.py's MONITORED_PROMPTS.
SOURCE_TO_PROMPT = {
    "tomorrow_per_holding": "portfolio.tomorrow_watch",
    "news_feed": "portfolio.news_feed_annotation",
}

HORIZON = "1d"  # fastest judged signal — see track_record.py's rationale, reused here

# The comparison is "last RECENT_WINDOW_DAYS" vs. "the BASELINE_WINDOW_DAYS
# before that" (non-overlapping) — a trailing baseline, not a fixed
# historical anchor, so the bar a segment is held to moves with it rather
# than staying pinned to whatever accuracy looked like months ago.
RECENT_WINDOW_DAYS = 14
BASELINE_WINDOW_DAYS = 90
LOOKBACK_DAYS = RECENT_WINDOW_DAYS + BASELINE_WINDOW_DAYS

# Cold-start rule: both windows need at least this many scored predictions
# before a comparison is trusted at all. Below this for either side, log
# "insufficient sample" and take no action. Same "~10-20 real observations"
# intuition as prompt_monitor.py's MIN_SAMPLE_SIZE.
MIN_SAMPLE_SIZE = 20

# Minimum hit-rate drop (in percentage points, baseline -> recent) required
# to call it "degraded" rather than noise on a binary hit/miss series. 15pp
# matches prompt_gate.py's CASE_REGRESSION_BLOCK-style "clear the noise
# floor" reasoning — re-validate against real history (recent vs. recent)
# before trusting it blind, the same way prompt_gate.py's Phase 2 report
# asked to be sanity-checked against a self-comparison first.
MIN_DROP_PP = 15.0

# Don't re-alert the same source more than once a week even if it stays
# degraded every single day — the point is "someone should look at this",
# not a fresh ping every morning for an unresolved issue.
ALERT_COOLDOWN_DAYS = 7


def _format_alert(source: str, prompt_name: str | None, stats: dict) -> str:
    prompt_label = html.escape(prompt_name or "unknown prompt")
    return (
        f"⚠️ <b>Accuracy drift — {html.escape(source)}</b>\n"
        f"Hit rate: {stats['baseline_hit_rate_pct']:.1f}% "
        f"(n={stats['baseline_n']}, trailing {BASELINE_WINDOW_DAYS}d) "
        f"→ {stats['recent_hit_rate_pct']:.1f}% "
        f"(n={stats['recent_n']}, last {RECENT_WINDOW_DAYS}d) "
        f"— down {stats['drop_pp']:.1f}pp\n"
        f"Prompt to review: <code>{prompt_label}</code>\n"
        f"<i>Signal, not a verdict — could be prompt drift or a market regime "
        f"change. Nothing here reverts, promotes, or edits any prompt "
        f"automatically; a human decides what to do next.</i>"
    )


def evaluate(source: str, days: int = LOOKBACK_DAYS, *, now: datetime | None = None) -> dict:
    """Run the daily drift check for one segment. Never raises — any
    unexpected failure is caught and reported as action="error" rather than
    propagating (this is called from an admin-token endpoint that must
    return a clean response either way).

    Returns a dict always containing at least {"source", "prompt_name",
    "action", "reason"}; `action` is one of:
      "insufficient_sample"     — cold-start rule; no comparison was made.
      "no_action"                — compared, drop below MIN_DROP_PP.
      "already_alerted_recently" — degraded, but within ALERT_COOLDOWN_DAYS
                                    of the last alert for this source.
      "alerted"                  — degraded, Telegram send succeeded.
      "alert_send_failed"        — degraded, Telegram send failed/no-op
                                    (still logged to accuracy_alert_log).
      "error"                    — evaluate() caught an unexpected exception.
    """
    prompt_name = SOURCE_TO_PROMPT.get(source)
    try:
        rows = outcome_ledger.scored_rows(horizon=HORIZON, days=days)
        rows = [r for r in rows if (r.get("source") or "unknown") == source]

        if not rows:
            reason = f"no scored {HORIZON} predictions for source={source!r} in the last {days}d"
            logger.info("accuracy_monitor[%s]: insufficient_sample — %s", source, reason)
            return {"source": source, "prompt_name": prompt_name,
                     "action": "insufficient_sample", "reason": reason}

        today = (now or datetime.now(timezone.utc)).date()
        recent_cutoff = (today - timedelta(days=RECENT_WINDOW_DAYS)).isoformat()

        recent = [r for r in rows if (r.get("prediction_date") or "") >= recent_cutoff]
        baseline = [r for r in rows if (r.get("prediction_date") or "") < recent_cutoff]

        recent_n = len(recent)
        recent_hits = sum(1 for r in recent if r.get("hit"))
        baseline_n = len(baseline)
        baseline_hits = sum(1 for r in baseline if r.get("hit"))

        if recent_n < MIN_SAMPLE_SIZE or baseline_n < MIN_SAMPLE_SIZE:
            reason = (
                f"sample too small — recent_n={recent_n}, baseline_n={baseline_n} "
                f"(need >= {MIN_SAMPLE_SIZE} in both windows)"
            )
            logger.info("accuracy_monitor[%s]: insufficient_sample — %s", source, reason)
            return {"source": source, "prompt_name": prompt_name,
                     "action": "insufficient_sample", "reason": reason,
                     "recent_n": recent_n, "baseline_n": baseline_n}

        recent_rate = recent_hits / recent_n
        baseline_rate = baseline_hits / baseline_n
        drop_pp = round((baseline_rate - recent_rate) * 100, 1)

        stats = {
            "recent_n": recent_n, "recent_hit_rate_pct": round(recent_rate * 100, 1),
            "baseline_n": baseline_n, "baseline_hit_rate_pct": round(baseline_rate * 100, 1),
            "drop_pp": drop_pp,
        }

        if drop_pp < MIN_DROP_PP:
            reason = f"drop_pp={drop_pp} below MIN_DROP_PP={MIN_DROP_PP} — within noise floor"
            logger.info("accuracy_monitor[%s]: no_action — %s | %s", source, reason, stats)
            return {"source": source, "prompt_name": prompt_name,
                     "action": "no_action", "reason": reason, **stats}

        try:
            last = outcome_ledger.last_accuracy_alert(source, days=ALERT_COOLDOWN_DAYS)
        except Exception:
            logger.exception("accuracy_monitor[%s]: cooldown check failed, proceeding as if none", source)
            last = None
        if last:
            reason = (
                f"already alerted for this source on {last.get('created_at')} "
                f"(cooldown={ALERT_COOLDOWN_DAYS}d)"
            )
            logger.info("accuracy_monitor[%s]: already_alerted_recently — %s", source, reason)
            return {"source": source, "prompt_name": prompt_name,
                     "action": "already_alerted_recently", "reason": reason, **stats}

        message = _format_alert(source, prompt_name, stats)
        sent = telegram_bot.send_admin_alert(message)

        try:
            outcome_ledger.log_accuracy_alert(source, prompt_name, message=message, **stats)
        except Exception:
            logger.exception("accuracy_monitor[%s]: failed to persist alert-log row", source)

        action = "alerted" if sent else "alert_send_failed"
        reason = f"degraded {drop_pp}pp past MIN_DROP_PP={MIN_DROP_PP} — {action}"
        # This is the "notify" step. logger.warning reaches Sentry Logs for
        # this deployment (see CLAUDE.md "Sentry" section) regardless of
        # whether the Telegram send itself succeeded — so a degraded segment
        # is always visible somewhere even if TELEGRAM_ADMIN_CHAT_ID is unset.
        logger.warning("accuracy_monitor[%s]: %s | %s", source, reason, stats)
        return {"source": source, "prompt_name": prompt_name,
                 "action": action, "reason": reason, "message": message, **stats}
    except Exception as e:
        logger.exception("accuracy_monitor[%s]: evaluate() failed unexpectedly", source)
        return {"source": source, "prompt_name": prompt_name, "action": "error", "reason": str(e)}
