"""
Langfuse datasets + experiments — the native "better or worse?" view
=======================================================================
prompt_gate.py already answers "is candidate version B better than live
version A". Its answer goes to a terminal and then evaporates: nothing is
stored, nothing is comparable across runs, and the tool that owns the
prompt versions (Langfuse) never hears about it. This module mirrors that
same judgement into Langfuse as a DATASET RUN per prompt version, so the
comparison becomes a durable, side-by-side view next to the versions it
describes.

WHAT IS AND ISN'T THE SOURCE OF TRUTH: prompt_gate.py stays the authority.
Its BLOCK/IMPROVED/NO_CHANGE verdict, its thresholds, and its holdout rule
are unchanged and still the only thing that gates a promotion. This module
is a mirror — if Langfuse is down, unconfigured, or this whole file is
deleted, the gate keeps working exactly as before. Nothing here may ever
become a precondition for promoting a prompt.

WHY EXPERIMENTS RATHER THAN HAND-BUILT RUNS: the SDK (4.14.3) exposes
`run_experiment(data=..., task=..., evaluators=[...])` as the supported way
to produce a dataset run; the older per-item `.run()` context manager isn't
in this version's DatasetClient (which has exactly one method,
run_experiment). Verified against the installed package, not assumed —
this repo has already been bitten once by calling a Langfuse method that
didn't exist and silently no-op'ing (see the prompt_monitor revert bug).

WHY THE TASK RUNS N REPS INTERNALLY: an experiment runs each item once, but
this project's whole eval doctrine is "pass RATE, not pass/fail", because a
single LLM rep can't distinguish flaky from reliably broken (see
eval_runner.py's docstring). So the task function delegates to
eval_runner.run_case() — the same code the gate uses — and returns that
case's pass rate; the evaluator then records the rate as the score. One
dataset item = one eval case = N real LLM calls, and the doctrine survives
the move into Langfuse instead of being quietly traded away for a tidier
integration.

PRIVACY: dataset items built from miss fixtures carry a real user's CONTEXT
snapshot. That is only permissible under the 2026-08-16 content-capture
decision (see llm_trace.py's docstring and
memory/gotcha_langfuse_content_capture.md). If that decision is ever
reversed, `sync_dataset(include_miss_fixtures=False)` is the switch that
keeps this module usable with hand-written cases only.

Public API:
    dataset_name_for(prompt_name) -> str
    sync_dataset(prompt_name, cases, include_miss_fixtures=True) -> dict
    run_version_experiment(prompt_name, prompt_text, cases, label, ...) -> dict
    mirror_gate_report(report, baseline_text, candidate_text, cases, ...) -> dict
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.services.observability import langfuse_client

logger = logging.getLogger(__name__)

# One dataset per managed prompt, rather than one shared dataset with a
# prompt_name column: Langfuse's compare view works within a dataset, and
# comparing a tomorrow-watch run against a news-feed run is meaningless.
DATASET_PREFIX = "evals"

# Cap on how many miss fixtures get synced. The gate's own runtime is
# N reps x 2 versions x items, so an unbounded fixture table would silently
# turn a gate run into an hours-long, expensive job. miss_fixtures grows
# forever by design; the eval set it feeds must not.
MAX_FIXTURE_ITEMS = 40


def dataset_name_for(prompt_name: str) -> str:
    return f"{DATASET_PREFIX}.{prompt_name}"


def _client_or_none():
    return langfuse_client.get_client()


def sync_dataset(
    prompt_name: str,
    cases: list[Any],
    *,
    include_miss_fixtures: bool = True,
) -> dict:
    """Create (if needed) the dataset for `prompt_name` and upsert one item
    per eval case.

    Item ids are deterministic (`<prompt_name>::<case_id>`) so re-running
    this is an upsert, not a duplicate-fest — the daily jobs and any manual
    CLI run can all call it freely.

    `expected_output` is left as the case's own description of what a pass
    looks like rather than a literal answer: our checks are Python
    predicates (see eval_runner.EvalCase.check), not string equality, and
    writing a fake "expected" string that nothing compares against would be
    worse than honest metadata. The real grading lives in the evaluator.

    Never raises. Returns a summary dict with counts and any error.
    """
    client = _client_or_none()
    if client is None:
        return {"status": "skipped", "reason": "langfuse not configured", "items": 0}

    name = dataset_name_for(prompt_name)
    try:
        client.create_dataset(
            name=name,
            description=(
                f"Eval cases for the Langfuse-managed prompt '{prompt_name}'. "
                "Synced from app/services/prompt_eval_cases.py (hand-written) "
                "and the miss_fixtures table (market-caught regressions). "
                "Source of truth is the repo/DB, not this dataset."
            ),
            metadata={"prompt_name": prompt_name, "synced_by": "langfuse_datasets.sync_dataset"},
        )
    except Exception:
        # Already exists is the overwhelmingly common case and is fine.
        logger.debug("create_dataset(%s) not created (likely exists)", name)

    written, failed = 0, 0
    for case in cases:
        try:
            client.create_dataset_item(
                dataset_name=name,
                id=f"{prompt_name}::{case.id}",
                input=case.context,
                expected_output={"schema": case.schema_description},
                metadata={
                    "case_id": case.id,
                    "prompt_name": case.prompt_name,
                    "holdout": bool(getattr(case, "holdout", False)),
                    "origin": "miss_fixture" if str(case.id).startswith("miss_") else "handwritten",
                },
            )
            written += 1
        except Exception:
            logger.exception("sync_dataset: item %r failed", getattr(case, "id", "?"))
            failed += 1

    out = {"status": "ok", "dataset": name, "items": written, "failed": failed}
    if include_miss_fixtures:
        out["note"] = (
            "miss-fixture cases carry real user context — permitted only under the "
            "2026-08-16 content-capture decision"
        )
    try:
        client.flush()
    except Exception:
        logger.exception("sync_dataset: flush failed")
    return out


def _build_task(prompt_text: str, case_by_id: dict[str, Any], n: int):
    """Experiment task: run one dataset item's eval case N times.

    Returns the pass-rate payload rather than a raw model response, because
    the unit this project judges is a rate over N reps, not one completion
    (see module docstring).
    """
    from app.services.pathback import eval_runner

    def task(*, item: Any, **_: Any) -> dict:
        case_id = None
        try:
            meta = getattr(item, "metadata", None) or {}
            case_id = meta.get("case_id")
        except Exception:
            pass
        case = case_by_id.get(case_id) if case_id else None
        if case is None:
            return {"error": f"no eval case for item {case_id!r}", "pass_rate": 0.0}
        result = eval_runner.run_case(case, prompt_text, n=n)
        return {
            "case_id": result.case_id,
            "pass_rate": result.pass_rate,
            "passes": result.passes,
            "n": result.n,
            "errors": result.errors,
            "raw_results": result.raw_results,
        }

    return task


def _pass_rate_evaluator(*, input: Any = None, output: Any = None,
                         expected_output: Any = None, metadata: Any = None, **_: Any):
    """Deterministic evaluator — records the pass rate and error count.

    No LLM judge here, deliberately: same stance as eval_runner.py and
    langfuse_scores.py. The value is a plain number the task already
    computed from Python predicates with known-correct answers.
    """
    from langfuse import Evaluation

    out = output if isinstance(output, dict) else {}
    rate = float(out.get("pass_rate") or 0.0)
    evals = [
        Evaluation(
            name="eval.pass_rate", value=rate, data_type="NUMERIC",
            comment=f"{out.get('passes', 0)}/{out.get('n', 0)} reps passed",
        ),
    ]
    if out.get("errors"):
        evals.append(Evaluation(
            name="eval.errors", value=float(out["errors"]), data_type="NUMERIC",
            comment="reps that raised or returned unparseable JSON",
        ))
    return evals


def run_version_experiment(
    prompt_name: str,
    prompt_text: str,
    cases: list[Any],
    *,
    label: str,
    n: int = 5,
    description: str | None = None,
) -> dict:
    """Run every case against one prompt version's text as a Langfuse
    dataset run, so the result is visible next to the prompt itself.

    `label` names the run (e.g. "v1-baseline", "v2-candidate"). Two runs
    with different labels over the same dataset are what Langfuse's compare
    view diffs.

    Never raises — returns {"status": "skipped"|"error"|"ok", ...}. The
    caller (prompt_gate mirroring, or a CLI) treats a failure here as
    cosmetic; the gate's own verdict is unaffected.
    """
    client = _client_or_none()
    if client is None:
        return {"status": "skipped", "reason": "langfuse not configured"}
    if not cases:
        return {"status": "skipped", "reason": "no cases"}

    dataset = dataset_name_for(prompt_name)
    case_by_id = {c.id: c for c in cases}
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    run_name = f"{label}-{stamp}"

    try:
        ds = client.get_dataset(dataset)
        items = [i for i in ds.items
                 if (getattr(i, "metadata", None) or {}).get("case_id") in case_by_id]
        if not items:
            return {"status": "skipped", "reason": f"dataset {dataset} has no matching items"}

        result = client.run_experiment(
            name=dataset,
            run_name=run_name,
            description=description or f"{prompt_name} — {label} — {n} reps/case",
            data=items,
            task=_build_task(prompt_text, case_by_id, n),
            evaluators=[_pass_rate_evaluator],
            max_concurrency=4,  # keep provider rate limits happy; these are real LLM calls
        )
        client.flush()
        return {
            "status": "ok",
            "dataset": dataset,
            "run_name": run_name,
            "items": len(items),
            "n": n,
            "result": _summarize_experiment(result),
        }
    except Exception as e:
        logger.exception("run_version_experiment(%s, %s) failed", prompt_name, label)
        return {"status": "error", "error": f"{type(e).__name__}: {e}", "run_name": run_name}


def _summarize_experiment(result: Any) -> dict:
    """Best-effort compaction of an ExperimentResult for a JSON response."""
    try:
        items = getattr(result, "item_results", None) or []
        rates = []
        for it in items:
            out = getattr(it, "output", None)
            if isinstance(out, dict) and out.get("pass_rate") is not None:
                rates.append(float(out["pass_rate"]))
        return {
            "items": len(items),
            "mean_pass_rate": round(sum(rates) / len(rates), 3) if rates else None,
        }
    except Exception:
        return {}


def mirror_gate_report(
    prompt_name: str,
    baseline_text: str,
    candidate_text: str,
    cases: list[Any],
    *,
    n: int = 5,
    baseline_label: str = "baseline",
    candidate_label: str = "candidate",
) -> dict:
    """Produce both sides of a gate comparison as Langfuse dataset runs.

    IMPORTANT — this RE-RUNS the cases; it does not replay prompt_gate's
    numbers. Two independent runs of the same comparison will differ
    slightly, because the underlying model is not deterministic (the exact
    reason the gate uses N reps and a noise-floor threshold in the first
    place). So treat this as "a second, visible run of the same experiment",
    not as a transcript of the gate's run. If you need them to be the same
    numbers, read the gate's report — that's the one that decides.

    Cost note: this doubles the LLM spend of a gate cycle. Call it when you
    want the durable side-by-side, not on every iteration of tweaking a
    candidate's wording.
    """
    sync = sync_dataset(prompt_name, cases)
    if sync.get("status") == "skipped":
        return {"status": "skipped", "reason": sync.get("reason"), "sync": sync}

    baseline = run_version_experiment(
        prompt_name, baseline_text, cases, label=baseline_label, n=n,
    )
    candidate = run_version_experiment(
        prompt_name, candidate_text, cases, label=candidate_label, n=n,
    )
    return {"status": "ok", "sync": sync, "baseline": baseline, "candidate": candidate}
