"""
Miss -> fixture converter — path-back leg 3d
================================================
Daily idempotent job (see app/routers/miss_fixtures.py's admin-token
endpoint, same shape as the other three daily jobs) that turns a
market-graded MISS into a permanent eval fixture, the same way a human
catching something wrong in real output becomes one (see
app/services/prompt_eval_cases.py — hand-authored, checked into git).
Before this job existed, a miss the market caught three days later
dead-ended at the /accuracy page; now it becomes a case eval_runner.py can
run against any future prompt candidate, forever after.

WHAT COUNTS AS A MISS: a graded (hit=False) prediction at the 1d horizon
(fastest signal — matches track_record.py's own horizon choice) whose
direction wasn't 'mixed' (mixed is never scoreable, see outcome_ledger.
_hit_rule). Exactly the same `hit` flag driving /accuracy today — nothing
new is computed to decide "was this a miss".

WHAT THE FIXTURE ACTUALLY CHECKS: not "was the reasoning good" — no LLM
judges anything here, same non-negotiable as eval_runner.py. The check is
"does the candidate prompt, replayed against the EXACT context that was
live when the miss happened, get THIS ticker's direction right, where the
original call got it wrong". Ground truth is the market's own graded
direction (recomputed from return_pct via the same threshold rule
outcome_ledger._hit_rule uses — see _expected_direction below), not a
human-authored expectation.

WHY A SEPARATE (PRIVATE) TABLE, NOT prompt_eval_cases.py: that file's
fixtures are hand-authored with synthetic context, safe to check into git.
A miss fixture's context_snapshot is a REAL user's real portfolio/watchlist
at call time — it must never leave the private, service-role-only trust
boundary prompt_call_log already lives in (RLS enabled, no policies — see
that table's own comment in migration 008/010). load_miss_fixture_cases()
below builds EvalCase objects from this table AT RUNTIME; nothing about a
real miss is ever written to a checked-in file. See AGENTS.md rule 9 for
why this matters: ai_predictions (unlike prompt_call_log/miss_fixtures) is
publicly readable, which is exactly why context_snapshot never lives there.

IDEMPOTENT: `miss_fixtures.prediction_id` is UNIQUE — re-running the daily
job just re-discovers already-converted misses and no-ops on each (see
outcome_ledger.log_miss_fixture's duplicate-key handling).

NON-NEGOTIABLE, same shape as every other path-back component: every piece
degrades to a no-op on missing data (no call_id, no stored context, no
Supabase) rather than erroring; convert_pending_misses() itself never
raises into its caller.

Public API:
    convert_pending_misses(days=LOOKBACK_DAYS, limit=MAX_PER_RUN) -> dict
    load_miss_fixture_cases(prompt_name, limit=50) -> list[EvalCase]
"""

from __future__ import annotations

import logging

from app.services import accuracy_monitor, eval_runner, outcome_ledger

logger = logging.getLogger(__name__)

HORIZON = "1d"
LOOKBACK_DAYS = 30   # how far back to scan for newly graded misses each run
MAX_PER_RUN = 200    # cap per invocation so a big backlog can't blow up one request

# Schema text duplicated from portfolio_intelligence.py's real call sites
# (tomorrow_schema / schema local vars) and app/services/
# prompt_eval_cases.py's hand-written fixtures — same deliberate-duplication
# precedent as AGENTS.md rule 5's GROUNDING_CONTRACT. A drift here degrades
# a generated fixture's schema hint, it doesn't break anything at runtime;
# keep it in sync if the real schema changes.
_TOMORROW_SCHEMA = """{
  "per_holding": [
    {
      "ticker": str, "sector": str,
      "catalyst_type": "earnings" | "news" | "technical" | "sector_flow" | "mixed",
      "event_date": str | null, "days_to_event": int | null,
      "what_to_watch": str,
      "direction": "positive" | "negative" | "mixed" | "neutral",
      "importance": "high" | "medium" | "low",
      "sources": [ str ]
    }
  ],
  "macro_themes": [
    {
      "theme": str, "direction": "positive" | "negative" | "mixed",
      "affected_holdings": [ str ], "affected_sectors": [ str ],
      "mechanism": { "text": str, "source": str },
      "importance": "high" | "medium" | "low"
    }
  ],
  "overall_bias": "positive" | "negative" | "neutral",
  "confidence": "low" | "medium" | "high",
  "data_gaps": [ str, ... ]
}"""

_NEWS_SCHEMA = """{
  "items": [
    {
      "news_id": str, "headline": str, "source": str,
      "category": "stock_specific" | "sector" | "macro" | "global",
      "impact_level": "high" | "medium" | "low",
      "direction": "positive" | "negative" | "mixed",
      "affected_tickers": [ str ], "reason": str,
      "technical_context": str | null
    }
  ],
  "data_gaps": [ str, ... ]
}"""

_SCHEMA_BY_PROMPT = {
    "portfolio.tomorrow_watch": _TOMORROW_SCHEMA,
    "portfolio.news_feed_annotation": _NEWS_SCHEMA,
}

_MAX_TOKENS_BY_PROMPT = {
    "portfolio.tomorrow_watch": 2200,
    "portfolio.news_feed_annotation": 2400,
}


def _tomorrow_check(ticker: str, expected: str):
    def _check(result: dict) -> bool:
        items = {w.get("ticker"): w for w in (result.get("per_holding") or [])}
        item = items.get(ticker)
        return item is not None and item.get("direction") == expected
    return _check


def _news_check(ticker: str, expected: str):
    def _check(result: dict) -> bool:
        for it in (result.get("items") or []):
            if ticker in (it.get("affected_tickers") or []):
                return it.get("direction") == expected
        return False
    return _check


_CHECK_BUILDER = {
    "portfolio.tomorrow_watch": _tomorrow_check,
    "portfolio.news_feed_annotation": _news_check,
}

# news_feed_annotation's schema has no 'neutral' option (positive|negative|
# mixed only, see _NEWS_SCHEMA above) — a miss whose market-graded ground
# truth is 'neutral' can't be represented as a fixture check for that
# prompt (the model would have to guess a value its own schema forbids).
# Skip converting it rather than writing a fixture that can never pass.
_UNREPRESENTABLE_DIRECTIONS = {
    "portfolio.news_feed_annotation": {"neutral"},
}


def _expected_direction(return_pct: float) -> str:
    """What direction WOULD have been a hit, given the graded return —
    the inverse of outcome_ledger._hit_rule's threshold logic, reusing its
    HIT_THRESHOLD_PCT constant so the two never drift apart. Deterministic;
    no LLM involved, same non-negotiable as eval_runner.py."""
    if return_pct >= outcome_ledger.HIT_THRESHOLD_PCT:
        return "positive"
    if return_pct <= -outcome_ledger.HIT_THRESHOLD_PCT:
        return "negative"
    return "neutral"


def convert_pending_misses(days: int = LOOKBACK_DAYS, limit: int = MAX_PER_RUN) -> dict:
    """Scan recently graded misses and convert each one that has a usable
    stored context into a permanent eval fixture. Idempotent — a prediction
    already converted is silently skipped (UNIQUE constraint on
    prediction_id in the miss_fixtures table).

    Never raises — returns a summary dict; every skip reason is counted,
    not silently dropped (the "log every decision, including no-ops"
    principle this whole path-back system follows).
    """
    summary = {
        "scanned": 0, "converted": 0,
        "skipped_unmonitored_source": 0, "skipped_no_call_id": 0,
        "skipped_no_context": 0, "skipped_unrepresentable_direction": 0,
        "skipped_already_exists": 0, "errors": 0,
    }
    try:
        misses = outcome_ledger.graded_misses(horizon=HORIZON, days=days)
    except Exception:
        logger.exception("miss_fixtures: graded_misses fetch failed")
        summary["errors"] += 1
        return summary

    for m in misses[:limit]:
        summary["scanned"] += 1
        try:
            prompt_name = accuracy_monitor.SOURCE_TO_PROMPT.get(m.get("source") or "")
            if not prompt_name:
                summary["skipped_unmonitored_source"] += 1
                continue

            call_id = (m.get("metadata") or {}).get("call_id")
            if not call_id:
                summary["skipped_no_call_id"] += 1
                continue

            call_ctx = outcome_ledger.call_context(call_id)
            context_snapshot = (call_ctx or {}).get("context_snapshot")
            if not context_snapshot:
                summary["skipped_no_context"] += 1
                continue

            return_pct = m.get("return_pct")
            if return_pct is None:
                summary["skipped_no_context"] += 1  # shouldn't happen for a graded row; same bucket
                continue
            expected = _expected_direction(return_pct)

            if expected in _UNREPRESENTABLE_DIRECTIONS.get(prompt_name, set()):
                summary["skipped_unrepresentable_direction"] += 1
                continue

            written = outcome_ledger.log_miss_fixture(
                m["prediction_id"], prompt_name,
                ticker=m["ticker"], prediction_date=m["prediction_date"],
                catalyst_type=m.get("catalyst_type"),
                original_direction=m["direction"], expected_direction=expected,
                reason=m.get("reason"), return_pct=return_pct,
                context_snapshot=context_snapshot,
            )
            if written:
                summary["converted"] += 1
                logger.info(
                    "miss_fixtures: converted %s %s (%s -> %s, return=%.2f%%)",
                    prompt_name, m["ticker"], m["direction"], expected, return_pct,
                )
            else:
                summary["skipped_already_exists"] += 1
        except Exception:
            logger.exception(
                "miss_fixtures: conversion failed for prediction %s", m.get("prediction_id"),
            )
            summary["errors"] += 1

    logger.info("miss_fixtures: run complete — %s", summary)
    return summary


def load_miss_fixture_cases(prompt_name: str, limit: int = 50) -> list[eval_runner.EvalCase]:
    """Build EvalCase objects from stored miss fixtures for `prompt_name`,
    runnable through eval_runner.py / prompt_gate.py exactly like the
    hand-written cases in prompt_eval_cases.py. Never raises — returns []
    if the prompt isn't one this module knows how to check, the ledger is
    unavailable, or the fetch fails (same best-effort posture as everything
    else reading from outcome_ledger).
    """
    schema = _SCHEMA_BY_PROMPT.get(prompt_name)
    check_builder = _CHECK_BUILDER.get(prompt_name)
    if not schema or not check_builder:
        return []
    try:
        rows = outcome_ledger.miss_fixture_rows(prompt_name, limit=limit)
    except Exception:
        logger.exception("miss_fixtures: load_miss_fixture_cases fetch failed for %s", prompt_name)
        return []

    max_tokens = _MAX_TOKENS_BY_PROMPT.get(prompt_name, 2200)
    cases: list[eval_runner.EvalCase] = []
    for r in rows:
        ctx = r.get("context_snapshot")
        ticker = r.get("ticker")
        expected = r.get("expected_direction")
        if not ctx or not ticker or not expected:
            continue
        cases.append(eval_runner.EvalCase(
            id=f"miss.{prompt_name}.{ticker}.{r.get('prediction_date')}",
            prompt_name=prompt_name,
            context=ctx,
            schema_description=schema,
            check=check_builder(ticker, expected),
            max_tokens=max_tokens,
        ))
    return cases
