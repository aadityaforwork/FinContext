"""
Grounding monitor — independent contract-compliance trigger
============================================================

This is deliberately separate from accuracy_monitor.py. Market outcomes ask
"was the direction right?"; this monitor asks "did the call honor the output
contract?" A prompt can fail either one independently, so neither signal is
collapsed into the other.

Every eligible call already has deterministic scores and any failed call has
an exact private transcript fixture. This daily job aggregates one strict
score for one prompt, alerts when the failure rate is material, and writes a
grounding_alert_log row. It never edits or relabels a prompt.
"""

from __future__ import annotations

import html
import logging

from app.services.notify import telegram_bot
from app.services.outcomes import outcome_ledger

logger = logging.getLogger(__name__)

MONITORED_PROMPTS = (
    "portfolio.movers_attribution",
    "portfolio.tomorrow_watch",
    "portfolio.news_feed_annotation",
)

VIOLATION_TYPES = (
    "grounding.schema_valid",
    "grounding.citation_coverage",
    "grounding.citation_validity",
    "grounding.confidence_honest",
)

LOOKBACK_DAYS = 7
MIN_SAMPLE_SIZE = 5
MAX_FAILURE_RATE_PCT = 20.0
ALERT_COOLDOWN_DAYS = 7


def _score_number(score: dict) -> float | None:
    value = score.get("value") if isinstance(score, dict) else None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate(
    prompt_name: str,
    violation_type: str,
    *,
    rows: list[dict] | None = None,
    days: int = LOOKBACK_DAYS,
) -> dict:
    """Evaluate one prompt/rule pair. Never raises."""
    base = {"prompt_name": prompt_name, "violation_type": violation_type}
    try:
        if prompt_name not in MONITORED_PROMPTS or violation_type not in VIOLATION_TYPES:
            return {**base, "action": "unmonitored", "reason": "unsupported prompt or score"}

        all_rows = rows if rows is not None else outcome_ledger.grounding_score_rows(days=days)
        eligible = []
        for row in all_rows:
            if row.get("prompt_name") != prompt_name:
                continue
            score = (row.get("grounding_scores") or {}).get(violation_type)
            value = _score_number(score)
            if value is not None:
                eligible.append(value)

        recent_n = len(eligible)
        if recent_n < MIN_SAMPLE_SIZE:
            return {
                **base,
                "action": "insufficient_sample",
                "reason": f"recent_n={recent_n}; need >= {MIN_SAMPLE_SIZE}",
                "recent_n": recent_n,
            }

        failure_n = sum(1 for value in eligible if value < 1.0)
        failure_rate_pct = round(failure_n / recent_n * 100, 1)
        stats = {
            "recent_n": recent_n,
            "failure_n": failure_n,
            "failure_rate_pct": failure_rate_pct,
            "threshold_pct": MAX_FAILURE_RATE_PCT,
        }
        if failure_rate_pct < MAX_FAILURE_RATE_PCT:
            return {
                **base,
                "action": "no_action",
                "reason": f"failure rate below {MAX_FAILURE_RATE_PCT}% threshold",
                **stats,
            }

        last = outcome_ledger.last_grounding_alert(
            prompt_name,
            violation_type,
            days=ALERT_COOLDOWN_DAYS,
        )
        if last:
            return {
                **base,
                "action": "already_alerted_recently",
                "reason": f"last alert at {last.get('created_at')}",
                **stats,
            }

        message = (
            f"⚠️ <b>Grounding contract drift — {html.escape(prompt_name)}</b>\n"
            f"Rule: <code>{html.escape(violation_type)}</code>\n"
            f"Failures: {failure_n}/{recent_n} ({failure_rate_pct:.1f}%) over {days}d; "
            f"threshold {MAX_FAILURE_RATE_PCT:.1f}%\n"
            "<i>This is independent of market accuracy. Exact failing transcripts "
            "are stored as private grounding fixtures; no prompt was edited.</i>"
        )
        sent = telegram_bot.send_admin_alert(message)
        outcome_ledger.log_grounding_alert(
            prompt_name,
            violation_type,
            message=message,
            **stats,
        )
        action = "alerted" if sent else "alert_send_failed"
        logger.warning(
            "grounding_monitor[%s/%s]: %s | %s",
            prompt_name,
            violation_type,
            action,
            stats,
        )
        return {
            **base,
            "action": action,
            "reason": "contract failure threshold crossed",
            "message": message,
            **stats,
        }
    except Exception as exc:
        logger.exception("grounding_monitor[%s/%s] failed", prompt_name, violation_type)
        return {**base, "action": "error", "reason": str(exc)}


def run_all(days: int = LOOKBACK_DAYS) -> dict:
    """Evaluate every supported prompt/rule pair from one database snapshot."""
    rows = outcome_ledger.grounding_score_rows(days=days)
    results = {}
    for prompt_name in MONITORED_PROMPTS:
        results[prompt_name] = {
            violation: evaluate(prompt_name, violation, rows=rows, days=days) for violation in VIOLATION_TYPES
        }
    return results
