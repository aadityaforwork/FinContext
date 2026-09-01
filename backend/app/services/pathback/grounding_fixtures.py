"""
Grounding fixtures — concrete contract failures for prompt repair
=================================================================

Market misses and grounding violations answer different questions and stay
in different queues. This module turns the latter into two useful forms:

* exact drafting evidence: the real task, CONTEXT, broken output, violated
  rule, and deterministic scorer detail;
* replayable EvalCases whose check is the same deterministic grounding score
  that originally failed.

The exact transcript lives only in private `prompt_call_log` (migration 016).
`grounding_fixtures` is a lightweight FK/index table, so no raw portfolio or
watchlist context is copied into a third store or into public ai_predictions.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from app.services.observability import langfuse_scores
from app.services.outcomes import outcome_ledger
from app.services.pathback.eval_runner import EvalCase

SUPPORTED_VIOLATIONS = {
    "grounding.schema_valid",
    "grounding.citation_coverage",
    "grounding.citation_validity",
    "grounding.confidence_honest",
}


def _passes_violation(violation_type: str, result: dict, context: dict) -> bool:
    score = langfuse_scores.grounding_scores(result, context).get(violation_type)
    if score is None:
        # In particular, emitting no {text, source} claims must not "fix"
        # citation validity by making the metric disappear.
        return False
    value = score.value
    if isinstance(value, bool):
        return value
    try:
        return float(value) >= 1.0
    except (TypeError, ValueError):
        return False


def _check_for(violation_type: str, context: dict) -> Callable[[dict], bool]:
    return lambda result: _passes_violation(violation_type, result, context)


def load_grounding_fixture_cases(prompt_name: str, limit: int = 50) -> list[EvalCase]:
    """Replay concrete contract violations through prompt_gate.

    Each case checks the exact rule that failed. Hand-written cases are still
    added separately by prompt_drafter, preventing a candidate from satisfying
    these fixtures by becoming empty, all-null, or otherwise useless.
    """
    rows = outcome_ledger.grounding_fixture_rows(prompt_name, limit=limit)
    cases: list[EvalCase] = []
    for row in rows:
        violation = row.get("violation_type")
        context = row.get("context_snapshot")
        schema = row.get("schema_description")
        fixture_id = row.get("id")
        if (
            violation not in SUPPORTED_VIOLATIONS
            or not isinstance(context, dict)
            or not schema
            or not fixture_id
        ):
            continue
        cases.append(
            EvalCase(
                id=f"grounding.{fixture_id}.{violation.rsplit('.', 1)[-1]}",
                prompt_name=prompt_name,
                context=context,
                schema_description=str(schema),
                check=_check_for(violation, context),
                max_tokens=2200,
            )
        )
    return cases


def build_drafting_evidence(prompt_name: str, limit: int = 8) -> str:
    """Exact newest transcript plus compact rule summaries for nearby failures.

    One full transcript is enough to give the drafting model a worked target
    without multiplying a large real CONTEXT eight times when one call failed
    more than one rule. The latest distinct call is included verbatim.
    """
    rows = outcome_ledger.grounding_fixture_rows(prompt_name, limit=limit)
    if not rows:
        return "(no concrete grounding fixture available)"

    newest = rows[0]
    same_call = [r for r in rows if r.get("call_id") == newest.get("call_id")]
    violations = "\n".join(
        f"- {r.get('violation_type')}={r.get('score_value')}: "
        f"{r.get('violation_detail') or 'no scorer detail'}"
        for r in same_call
    )
    nearby = [r for r in rows if r.get("call_id") != newest.get("call_id")]
    nearby_summary = (
        "\n".join(
            f"- call {r.get('call_id')}: {r.get('violation_type')}={r.get('score_value')} "
            f"({r.get('violation_detail') or 'no detail'})"
            for r in nearby
        )
        or "(none)"
    )

    return (
        "EXACT FAILING TRANSCRIPT (verbatim JSON serialization):\n"
        f"Violated rules:\n{violations}\n\n"
        f"TASK:\n{newest.get('task_text') or '(missing)'}\n\n"
        f"CONTEXT:\n{json.dumps(newest.get('context_snapshot'), ensure_ascii=False, default=str)}\n\n"
        f"BROKEN OUTPUT:\n{json.dumps(newest.get('output_snapshot'), ensure_ascii=False, default=str)}\n\n"
        f"OTHER RECENT VIOLATIONS:\n{nearby_summary}"
    )
