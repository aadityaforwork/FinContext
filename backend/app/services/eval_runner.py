"""
Eval runner — Phase 1 foundation for the prompt-version judge
================================================================
Prompts are already versioned in Langfuse (see prompt_registry.py / AGENTS.md
path-back leg 3b), fetched by the `production` label with a hardcoded
fallback. Nothing decided whether a version was actually *good* before it
went live — this module is the first piece of that: a small, deterministic
way to run a named `EvalCase` against a prompt's text N times and get back a
pass rate instead of a single pass/fail boolean.

Why N repeats instead of one: an LLM call is not deterministic even at low
temperature. A single run's pass/fail is itself noisy — this is the same
reason track_record.py uses hierarchical shrinkage instead of a raw hit-rate
off a handful of observations (see that module's docstring). Repeating each
case and reporting `passes/n` gives the two features built on top of this
(the offline comparison gate — Phase 2 — and the online monitor — Phase 3)
something less noisy to threshold against. This module doesn't do any
thresholding itself; it just runs cases and counts.

NO LLM JUDGES ANYTHING HERE. Every `EvalCase.check` is a plain deterministic
Python predicate over the parsed JSON response — substring/schema/field
checks with a known-correct answer, the same style as
tests/evals/test_grounding_live.py's live assertions. This module doesn't
introduce a new evaluation *philosophy*, just a way to run the existing
"known question, known-correct answer shape" style of check N times and
tabulate it instead of asserting it once.

Best-effort / never raises into a caller: a case whose LLM call raises, times
out, or returns unparseable JSON is counted as a failed run (and tracked
separately in `CaseResult.errors`) — it does not abort the batch and it does
not propagate. Same failure stance as outcome_ledger.py and track_record.py:
a broken eval run degrades to "this case failed this rep", not a crash.

Public API:
    EvalCase(id, prompt_name, context, schema_description, check, ...)
    run_case(case, prompt_text, n=DEFAULT_N) -> CaseResult
    run_cases(cases, prompt_text, n=DEFAULT_N) -> list[CaseResult]
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# How many times to run each case against a given prompt text when the
# caller doesn't specify. 5 is small enough to keep a gate run's LLM spend
# bounded (see Phase 2's module docstring for the actual cost math) while
# still being enough repeats to see a case that's flaky rather than reliably
# broken — a single rep can't distinguish those two.
DEFAULT_N = 5


@dataclass(frozen=True)
class EvalCase:
    """One deterministic-outcome eval case.

    `prompt_name` ties the case to the Langfuse-managed prompt it exercises
    (e.g. "portfolio.tomorrow_watch") — purely documentation/grouping, this
    module doesn't fetch prompts itself; callers pass `prompt_text` into
    run_case/run_cases explicitly so the same case can be run against two
    different versions' text (see the Phase 2 comparison gate).

    `check(result) -> bool` must be a pure, deterministic function of the
    parsed JSON response — no LLM calls inside it. It receives {} on a parse
    failure (same shape ai_client.generate_grounded_json returns on failure)
    and is expected to return False for that input, not raise; run_case
    guards it anyway (see below) so a buggy check can't crash a run.

    `holdout`: excluded from anything that treats a case set as "iterate
    against this" (Phase 2's comparison gate) — reserved for cases used only
    to sanity-check a candidate before it ever gets promoted, so a prompt
    can't be tuned specifically to the cases it's graded on. Not consumed by
    this module at all; it's metadata for the gate to read.
    """

    id: str
    prompt_name: str
    context: dict
    schema_description: str
    check: Callable[[dict], bool]
    max_tokens: int = 600
    holdout: bool = False


@dataclass
class CaseResult:
    case_id: str
    prompt_name: str
    n: int
    passes: int
    errors: int  # subset of (n - passes): calls that raised or returned unparseable JSON
    pass_rate: float
    raw_results: list[bool] = field(default_factory=list)  # per-rep pass/fail, for debugging noise


def run_case(case: EvalCase, prompt_text: str, n: int = DEFAULT_N) -> CaseResult:
    """Run one eval case `n` times against `prompt_text`. Never raises —
    any exception from the LLM call or from `case.check` itself is caught,
    logged, and counted as a failed (and errored) rep so one bad case can't
    abort a batch run (see run_cases)."""
    from app.services import ai_client  # local import: avoid import cost for callers that only build cases

    raw: list[bool] = []
    errors = 0
    for i in range(n):
        ok = False
        try:
            result = ai_client.generate_grounded_json(
                task=prompt_text,
                context=case.context,
                schema_description=case.schema_description,
                max_tokens=case.max_tokens,
            )
            if result:
                ok = bool(case.check(result))
        except Exception:
            logger.exception("eval_runner: case %r rep %d/%d raised", case.id, i + 1, n)
            errors += 1
        raw.append(ok)

    passes = sum(raw)
    return CaseResult(
        case_id=case.id,
        prompt_name=case.prompt_name,
        n=n,
        passes=passes,
        errors=errors,
        pass_rate=round(passes / n, 3) if n else 0.0,
        raw_results=raw,
    )


def run_cases(cases: list[EvalCase], prompt_text: str, n: int = DEFAULT_N) -> list[CaseResult]:
    """Run every case in `cases` against the same `prompt_text`, n reps each.
    One case failing to run at all (see run_case's own try/except) never
    prevents the rest from running."""
    return [run_case(c, prompt_text, n) for c in cases]


def summarize(results: list[CaseResult]) -> dict[str, Any]:
    """Small rollup used by both the pytest report (Phase 1 "show me the pass
    rates") and Phase 2's comparison report: per-case pass rates plus an
    overall mean. Never raises; empty input -> zeros."""
    if not results:
        return {"cases": [], "overall_pass_rate": 0.0, "total_errors": 0}
    return {
        "cases": [
            {"case_id": r.case_id, "prompt_name": r.prompt_name, "n": r.n,
             "passes": r.passes, "pass_rate": r.pass_rate, "errors": r.errors}
            for r in results
        ],
        "overall_pass_rate": round(sum(r.pass_rate for r in results) / len(results), 3),
        "total_errors": sum(r.errors for r in results),
    }
