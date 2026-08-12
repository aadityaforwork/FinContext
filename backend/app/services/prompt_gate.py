"""
Prompt-version gate — Phase 2 (offline, blocks promotion)
============================================================
Compares two versions' TEXT of the same Langfuse-managed prompt against the
same eval case set (see eval_runner.py / tests/evals/prompt_gate_cases.py)
and produces a per-case pass-rate table plus a verdict for a human to read.

NEVER PROMOTES. This module never calls Langfuse's `update_prompt_labels`
and never writes a `production` label — see AGENTS.md ("forward promotion
is a human action") and prompt_registry.py's module docstring. Its only
output is a report; what a human does with that report (relabel a
`candidate` version to `production` in the Langfuse UI, or don't) is
entirely outside this module.

Three possible verdicts:
  BLOCK      — at least one active case's pass rate dropped by more than
               CASE_REGRESSION_BLOCK. Blocks regardless of how the overall
               average looks — a candidate that improves 9 cases while
               quietly breaking a 10th is still a regression on that 10th
               case, and averaging would hide exactly the failure this gate
               exists to catch.
  IMPROVED   — no case blocked, AND the overall (mean across active cases)
               pass rate improved by at least MIN_OVERALL_IMPROVEMENT.
  NO_CHANGE  — everything else. A candidate that's slightly *better* but
               under MIN_OVERALL_IMPROVEMENT is NO_CHANGE, not IMPROVED —
               "anything smaller counts as no change, never an
               improvement" (see the two threshold constants below for why
               "smaller" has to mean something bigger than zero: run this
               module comparing a prompt against its own literal text and
               the delta you get back is pure LLM sampling noise, not
               signal — these thresholds have to clear that noise floor or
               every gate run is a coin flip).

HOLDOUT: an EvalCase with holdout=True is excluded from the case set this
module runs UNLESS include_holdout=True is passed explicitly. Standard
train/holdout split reasoning: a human iterating on candidate wording keeps
re-running this gate against the same visible cases while tuning — if
holdout cases were part of that loop, the candidate could end up implicitly
tuned to them too, defeating the point of having an independent check.
Call compare(..., include_holdout=True) once, at the end, right before
asking a human to promote — not on every iteration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from app.services import eval_runner
from app.services.eval_runner import CaseResult, EvalCase

logger = logging.getLogger(__name__)

# A single case's pass rate must drop by at least this many percentage
# points (0-1 scale), candidate vs baseline, to BLOCK on its own. Set above
# the smallest non-zero swing a single flipped rep can cause at the default
# N (1/DEFAULT_N = 0.20 at N=5) — a lone flipped rep out of five must not be
# able to block a promotion by itself. Calibrated against an actual
# self-comparison run (same prompt text on both sides — see
# scripts/prompt_gate.py's --baseline-label/--candidate-label pointed at the
# same label) rather than picked blind; re-run that self-check and raise
# this further if a noisier case/model combination ever produces bigger
# swings than this leaves room for.
CASE_REGRESSION_BLOCK = 0.34

# Overall (mean across active cases) pass-rate improvement required to call
# a candidate IMPROVED rather than NO_CHANGE. Same noise-floor reasoning as
# CASE_REGRESSION_BLOCK, just applied to the aggregate instead of a single
# case.
MIN_OVERALL_IMPROVEMENT = 0.15

DEFAULT_N = eval_runner.DEFAULT_N


class Verdict(str, Enum):
    BLOCK = "BLOCK"
    IMPROVED = "IMPROVED"
    NO_CHANGE = "NO_CHANGE"


@dataclass(frozen=True)
class CaseComparison:
    case_id: str
    prompt_name: str
    baseline: CaseResult
    candidate: CaseResult
    delta: float  # candidate.pass_rate - baseline.pass_rate
    blocked: bool  # this case alone tripped CASE_REGRESSION_BLOCK


@dataclass(frozen=True)
class GateReport:
    prompt_name: str | None
    n: int
    case_regression_block: float
    min_overall_improvement: float
    comparisons: list[CaseComparison]
    holdout_excluded: list[str]
    baseline_overall_pass_rate: float
    candidate_overall_pass_rate: float
    overall_delta: float
    verdict: Verdict
    blocked_cases: list[str]


def compare(
    cases: list[EvalCase],
    baseline_text: str,
    candidate_text: str,
    *,
    n: int = DEFAULT_N,
    include_holdout: bool = False,
    case_regression_block: float = CASE_REGRESSION_BLOCK,
    min_overall_improvement: float = MIN_OVERALL_IMPROVEMENT,
) -> GateReport:
    """Run `cases` (minus holdout ones, unless include_holdout=True) `n`
    times each against both `baseline_text` and `candidate_text`, and
    return a GateReport. Read-only: never touches Langfuse, never promotes,
    never writes a prompt or a label — see module docstring.

    An empty `cases` list (e.g. every case filtered out as holdout) returns
    a NO_CHANGE report with zero comparisons rather than raising or
    dividing by zero — there's nothing to judge, so nothing is asserted.
    """
    active = [c for c in cases if include_holdout or not c.holdout]
    active_ids = {c.id for c in active}
    excluded = [c.id for c in cases if c.id not in active_ids]

    comparisons: list[CaseComparison] = []
    blocked_cases: list[str] = []
    for case in active:
        baseline_result = eval_runner.run_case(case, baseline_text, n=n)
        candidate_result = eval_runner.run_case(case, candidate_text, n=n)
        delta = round(candidate_result.pass_rate - baseline_result.pass_rate, 3)
        blocked = delta <= -case_regression_block
        if blocked:
            blocked_cases.append(case.id)
        comparisons.append(CaseComparison(
            case_id=case.id, prompt_name=case.prompt_name,
            baseline=baseline_result, candidate=candidate_result,
            delta=delta, blocked=blocked,
        ))

    if comparisons:
        baseline_overall = round(sum(c.baseline.pass_rate for c in comparisons) / len(comparisons), 3)
        candidate_overall = round(sum(c.candidate.pass_rate for c in comparisons) / len(comparisons), 3)
    else:
        baseline_overall = candidate_overall = 0.0
    overall_delta = round(candidate_overall - baseline_overall, 3)

    if blocked_cases:
        verdict = Verdict.BLOCK
    elif overall_delta >= min_overall_improvement:
        verdict = Verdict.IMPROVED
    else:
        verdict = Verdict.NO_CHANGE

    prompt_names = {c.prompt_name for c in active}
    prompt_name = next(iter(prompt_names)) if len(prompt_names) == 1 else None

    return GateReport(
        prompt_name=prompt_name, n=n,
        case_regression_block=case_regression_block, min_overall_improvement=min_overall_improvement,
        comparisons=comparisons, holdout_excluded=excluded,
        baseline_overall_pass_rate=baseline_overall, candidate_overall_pass_rate=candidate_overall,
        overall_delta=overall_delta, verdict=verdict, blocked_cases=blocked_cases,
    )


def render_report(report: GateReport) -> str:
    """Plain-text report for a human. This is the only thing this module
    produces — nothing here triggers any automatic action."""
    lines = [
        f"Prompt gate report — {report.prompt_name or '(mixed case set)'}",
        f"N={report.n} reps/case  |  block if any case drops >= {report.case_regression_block:.0%}"
        f"  |  IMPROVED needs overall >= +{report.min_overall_improvement:.0%}",
    ]
    if report.holdout_excluded:
        lines.append(f"Holdout cases excluded from this run: {', '.join(report.holdout_excluded)}")
    if not report.comparisons:
        lines.append("(no active cases — nothing to compare)")
        lines.append(f"VERDICT: {report.verdict.value}")
        return "\n".join(lines)

    lines.append("-" * 82)
    lines.append(f"{'case':55s} {'baseline':>9s} {'candidate':>10s} {'delta':>8s}")
    for c in report.comparisons:
        flag = "  <-- BLOCK" if c.blocked else ""
        lines.append(
            f"{c.case_id:55s} {c.baseline.pass_rate:>8.0%} {c.candidate.pass_rate:>10.0%} "
            f"{c.delta:>+7.0%}{flag}"
        )
    lines.append("-" * 82)
    lines.append(
        f"overall: {report.baseline_overall_pass_rate:.0%} -> {report.candidate_overall_pass_rate:.0%} "
        f"({report.overall_delta:+.0%})"
    )
    lines.append(f"VERDICT: {report.verdict.value}")
    lines.append(
        "This report does not promote anything. Promotion (relabeling a Langfuse "
        "prompt version to `production`) is always a human action — see AGENTS.md."
    )
    return "\n".join(lines)
