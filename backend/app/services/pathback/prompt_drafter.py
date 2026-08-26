"""
Prompt drafter — path-back leg 3e: draft / test / approve agent
====================================================================
The piece that was "designed, not built" going into this session: when a
segment gets flagged (accuracy_monitor.py's drift alert), draft a revised
prompt, test it against the eval suite (prompt_gate.py — hand-written cases
in prompt_eval_cases.py PLUS the market-caught cases miss_fixtures.py has
been accumulating), and — if it clears the gate — create a Langfuse
`candidate` version and PAUSE, waiting for a human to actually promote it by
moving the label in the Langfuse UI. This is the first component in the
whole path-back system that has to survive a real wait for a person: a
Telegram alert fires now, but "a human moves a label" might happen an hour
later or three days later, from an entirely separate process/request. That
survive-a-pause requirement is why this module uses LangGraph — see "WHY
LANGGRAPH" below.

NEVER PROMOTES ITSELF. The only Langfuse write this module ever makes is
`create_prompt(..., labels=["candidate"])` — a NEW version, never labeled
`production`. Moving `production` to point at that version is a human
action in the Langfuse UI, full stop — same non-negotiable as prompt_
monitor.py's revert-only stance (AGENTS.md rule 8). This module doesn't even
have write access to a `production` label anywhere in its code path; the
only thing it ever confirms is whether a human already did that (see
check_pending_approvals).

WHAT TRIGGERS A RUN: run_pending_drafts() (a daily job, same admin-token
endpoint shape as every other path-back cron) scans accuracy_monitor.py's
alert log for alerts fired in the last ALERT_LOOKBACK_DAYS days. One alert
= one flagged prompt. A cooldown (prompt_draft_store.active_run_for_prompt)
stops it from starting a second draft attempt for the same prompt while a
prior one is still awaiting a human, or too soon after the last attempt
concluded either way.

WHY LANGGRAPH: everything upstream of this module (accuracy_monitor.py,
miss_fixtures.py, prompt_monitor.py) is a plain function that runs start to
finish inside one HTTP request and returns. This module can't work that way
— "pause until a human moves a Langfuse label" might span days, and nothing
about a Python call stack survives that gap on its own. LangGraph's
`interrupt()` primitive is built for exactly this: a node calls interrupt(),
the graph halts and returns control with the state checkpointed, and later
a completely separate call resumes it with `Command(resume=...)`, re-
entering the SAME node with the SAME state.

PERSISTENCE, THE PART LANGGRAPH DOESN'T SOLVE FOR US: `interrupt()` requires
a checkpointer, and LangGraph's own production-grade checkpointers
(langgraph-checkpoint-postgres, -sqlite) assume either a direct Postgres
connection string or a local disk file — neither fits this repo's existing
Supabase-via-REST-client pattern, and Render's local disk isn't guaranteed
durable across deploys (see AGENTS.md's crewai/Render deploy-fragility
gotcha for why "assume the local filesystem persists" has already bitten
this repo once). So: this module uses LangGraph's own `InMemorySaver`
(the reference implementation, correct by construction) for the actual
checkpoint logic, and wraps it with a thin snapshot/restore layer
(_dump_thread_state / _load_thread_state below) that pickles just the
interrupted thread's slice of that saver's internal dicts and stores it as
a base64 blob in `prompt_draft_checkpoints` (migration 011) via
prompt_draft_store.py — the same "durable state lives in a private Supabase
table" pattern every other path-back component already uses. This was
verified end-to-end in a standalone prototype before being wired in here:
build a graph, run it to an interrupt, dump the first InMemorySaver's
thread state, load it into a SECOND fresh InMemorySaver (simulating a
different process), and resume via Command(resume=...) — it reproduces
correctly. Nothing here reimplements LangGraph's own checkpoint semantics;
it only adds save/load around the untouched reference implementation.

NON-NEGOTIABLE, same shape as every other path-back component: every
top-level entry point below (start_draft_run, resume_approved_run,
check_pending_approvals, run_pending_drafts) never raises into its caller —
failures degrade to an "error" status/count and get logged, not propagated.

Public API:
    start_draft_run(prompt_name, trigger_reason) -> dict
    resume_approved_run(thread_id, resume_value) -> dict
    check_pending_approvals() -> dict
    run_pending_drafts(alert_lookback_days=ALERT_LOOKBACK_DAYS) -> dict
"""

from __future__ import annotations

import base64
import logging
import pickle
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, TypedDict

# LangGraph is imported LAZILY, inside the functions that actually need it —
# never at module scope. Measured 2026-08-15: `import langgraph` costs ~53 MB
# resident. This module is reached only through the admin-token-gated
# /api/prompt-drafter/* cron endpoints (once a day), but app/main.py imports
# every router at boot, so a module-scope import here loaded that 53 MB into
# the long-lived web process forever — ~10% of Render Starter's 512 MB cap,
# spent on a code path a served request never touches. That is the same rule
# crewai already follows everywhere in app/agents/ (see agents/base.py's
# prewarm() docstring for the OOM incident that established it).
#
# `from __future__ import annotations` above makes every annotation a string,
# so the TYPE_CHECKING block below is enough for type checkers and costs
# nothing at runtime.
if TYPE_CHECKING:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import StateGraph

from app.services.llm import ai_client
from app.services.notify import telegram_bot
from app.services.observability import langfuse_client, prompt_registry
from app.services.outcomes import outcome_ledger
from app.services.pathback import (
    accuracy_monitor,
    miss_fixtures,
    prompt_draft_store,
    prompt_eval_cases,
    prompt_gate,
)

logger = logging.getLogger(__name__)

# How far back to look for accuracy_monitor.py alerts when deciding what to
# draft against. Wider than that module's own 7-day re-alert cooldown so a
# segment flagged once still gets picked up by the very next daily
# run_pending_drafts() call, not just on the day the alert happened to fire.
ALERT_LOOKBACK_DAYS = 14

# Don't start a second draft attempt for the same prompt within this many
# days of the last one (regardless of how that one ended) — see
# prompt_draft_store.active_run_for_prompt's own docstring for the full
# rule (an 'awaiting_approval' run always blocks, independent of age).
DRAFT_RETRY_COOLDOWN_DAYS = 7

# A run that's been sitting in 'awaiting_approval' longer than this without
# a human moving the Langfuse label gets marked 'expired' by
# check_pending_approvals() rather than waiting forever — it stays fully
# visible in prompt_draft_runs either way, this just stops treating it as
# live worklist noise. A human can always still promote the candidate by
# hand later; nothing about the Langfuse version itself is deleted.
STALE_AFTER_DAYS = 21

_PROMPT_TO_SOURCE = {v: k for k, v in accuracy_monitor.SOURCE_TO_PROMPT.items()}

DRAFT_META_PROMPT = """You are revising an AI product's system prompt because its predictions have \
been measurably wrong more often lately, based on real market outcomes.

CURRENT PROMPT (what the model is told today):
---
{baseline_text}
---

WHY THIS NEEDS REVISION:
{trigger_reason}

RECENT MISSES (real predictions this prompt produced that the market later proved wrong):
{evidence}

Write a REVISED version of the prompt that:
- Targets the pattern behind these misses, if one is visible in the examples above -- don't \
make unrelated changes.
- Preserves every structural/schema instruction and rule already in the current prompt \
(field names, allowed enum values, banned phrases, output format) -- those are unrelated to \
this problem and must not change.
- Stays roughly the same length and style as the current prompt -- this is a targeted edit, \
not a rewrite from scratch.

Respond with ONLY the full revised prompt text. No commentary, no markdown code fences, no \
"Here is the revised prompt:" preamble -- just the prompt text itself, ready to use as-is in \
place of the current one."""


class DraftState(TypedDict, total=False):
    prompt_name: str
    trigger_reason: str
    baseline_text: str
    baseline_version: int | None
    evidence: str
    draft_text: str | None
    gate_summary: dict | None
    verdict: str | None
    candidate_version: int | None
    status: str
    approval_result: dict | None


# ---------------------------------------------------------------------------
# Evidence gathering — compact, deterministic, no context replay (that's
# what miss_fixtures.py's eval cases are for; this is just grounding text
# for the drafting LLM call, not something re-checked programmatically).
# ---------------------------------------------------------------------------
def _build_evidence(prompt_name: str, days: int = 30, limit: int = 8) -> str:
    source = _PROMPT_TO_SOURCE.get(prompt_name)
    try:
        misses = outcome_ledger.graded_misses(horizon="1d", days=days)
    except Exception:
        logger.exception("prompt_drafter: graded_misses fetch failed for %s", prompt_name)
        misses = []
    relevant = [m for m in misses if m.get("source") == source][:limit]
    if not relevant:
        return "(no specific miss examples available in the lookback window -- rely on the trigger reason above.)"
    lines = []
    for m in relevant:
        reason = (m.get("reason") or "").strip()[:200] or "no stated reason"
        lines.append(
            f"- {m.get('ticker')} on {m.get('prediction_date')}: predicted "
            f"'{m.get('direction')}' ({reason}) -- actual 1d return was {m.get('return_pct')}%."
        )
    return "\n".join(lines)


def _serialize_gate_report(report: prompt_gate.GateReport) -> dict:
    """JSON-safe subset of a GateReport, small enough to fit in a Telegram
    message and a checkpoint blob — not the full per-case raw_results."""
    return {
        "verdict": report.verdict.value,
        "n": report.n,
        "baseline_overall_pass_rate": report.baseline_overall_pass_rate,
        "candidate_overall_pass_rate": report.candidate_overall_pass_rate,
        "overall_delta": report.overall_delta,
        "blocked_cases": report.blocked_cases,
        "case_count": len(report.comparisons),
    }


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------
def _load_baseline(state: DraftState) -> dict:
    prompt_name = state["prompt_name"]
    # Local import: portfolio_intelligence.py is a FastAPI router module with
    # a heavy import chain (grounding.py, ai_client, etc.) this service
    # module would otherwise never need to load. These two constants are the
    # single source of truth for each prompt's hardcoded fallback text (used
    # by prompt_registry.get_prompt only when Langfuse itself is unset/
    # unreachable) -- importing them keeps this module byte-identical to the
    # real call sites' cold-start behavior instead of maintaining a second,
    # driftable copy (unlike the SCHEMA text duplicated in miss_fixtures.py/
    # prompt_eval_cases.py, which callers actually depend on structurally).
    from app.routers.portfolio_intelligence import (
        NEWS_FEED_ANNOTATION_FALLBACK_PROMPT,
        TOMORROW_WATCH_FALLBACK_PROMPT,
    )

    fallback = {
        "portfolio.tomorrow_watch": TOMORROW_WATCH_FALLBACK_PROMPT,
        "portfolio.news_feed_annotation": NEWS_FEED_ANNOTATION_FALLBACK_PROMPT,
    }.get(prompt_name, "")
    result = prompt_registry.get_prompt(prompt_name, fallback)
    return {
        "baseline_text": result.text,
        "baseline_version": result.version,
        "evidence": _build_evidence(prompt_name),
        "status": "running",
    }


def _draft_candidate(state: DraftState) -> dict:
    meta_prompt = DRAFT_META_PROMPT.format(
        baseline_text=state["baseline_text"],
        trigger_reason=state["trigger_reason"],
        evidence=state["evidence"],
    )
    try:
        draft = ai_client.generate_text(meta_prompt, max_tokens=2500, temperature=0.4)
    except Exception:
        logger.exception("prompt_drafter: draft generation failed for %s", state["prompt_name"])
        return {"draft_text": None, "status": "draft_failed"}

    draft = (draft or "").strip()
    if draft.startswith("```"):
        # Strip a stray markdown fence if the model added one despite being
        # told not to (e.g. "```text\n...\n```" or bare "```\n...\n```").
        draft = draft.strip("`").strip()
        if draft[:4].lower() == "text":
            draft = draft[4:].strip()
    if not draft:
        return {"draft_text": None, "status": "draft_failed"}
    return {"draft_text": draft}


def _route_after_draft(state: DraftState) -> str:
    return "run_gate" if state.get("draft_text") else "blocked"


def _run_gate(state: DraftState) -> dict:
    prompt_name = state["prompt_name"]
    cases = [c for c in prompt_eval_cases.ALL_CASES if c.prompt_name == prompt_name]
    try:
        cases = cases + miss_fixtures.load_miss_fixture_cases(prompt_name)
    except Exception:
        logger.exception("prompt_drafter: loading miss-fixture cases failed for %s", prompt_name)

    if not cases:
        return {
            "verdict": "NO_CHANGE",
            "gate_summary": {"reason": f"no eval cases available for {prompt_name}"},
        }

    report = prompt_gate.compare(cases, state["baseline_text"], state["draft_text"])
    return {"verdict": report.verdict.value, "gate_summary": _serialize_gate_report(report)}


def _route_after_gate(state: DraftState) -> str:
    verdict = state.get("verdict")
    if verdict == "IMPROVED":
        return "publish_candidate"
    if verdict == "BLOCK":
        return "blocked"
    return "no_change"


def _report_blocked(state: DraftState) -> dict:
    gate_summary = state.get("gate_summary") or {}
    draft_preview = (state.get("draft_text") or "")[:800]
    message = (
        f"🧪 <b>Prompt draft blocked — {state['prompt_name']}</b>\n"
        f"Trigger: {state['trigger_reason']}\n"
        f"Gate verdict: {state.get('verdict') or 'draft generation failed'}\n"
        f"Blocked cases: {gate_summary.get('blocked_cases') or '(n/a)'}\n"
        f"<i>No Langfuse candidate was created — the draft didn't clear the eval gate. "
        f"Drafted text (for reference, not applied anywhere):</i>\n"
        f"<code>{draft_preview}</code>"
    )
    telegram_bot.send_admin_alert(message)
    logger.info("prompt_drafter[%s]: blocked — %s", state["prompt_name"], gate_summary)
    return {"status": "blocked"}


def _report_no_change(state: DraftState) -> dict:
    gate_summary = state.get("gate_summary") or {}
    message = (
        f"🧪 <b>Prompt draft — {state['prompt_name']}: no improvement</b>\n"
        f"Trigger: {state['trigger_reason']}\n"
        f"Gate: baseline {gate_summary.get('baseline_overall_pass_rate')} -> "
        f"candidate {gate_summary.get('candidate_overall_pass_rate')} "
        f"({gate_summary.get('overall_delta')})\n"
        f"<i>Didn't clear the improvement threshold — no Langfuse candidate created.</i>"
    )
    telegram_bot.send_admin_alert(message)
    logger.info("prompt_drafter[%s]: no_change — %s", state["prompt_name"], gate_summary)
    return {"status": "no_change"}


def _publish_candidate(state: DraftState) -> dict:
    """The only Langfuse WRITE this whole module can ever make: create a new
    version labeled 'candidate' — never 'production'. See module docstring."""
    prompt_name = state["prompt_name"]
    client = langfuse_client.get_client()
    if client is None:
        logger.warning("prompt_drafter[%s]: gate IMPROVED but Langfuse isn't configured", prompt_name)
        telegram_bot.send_admin_alert(
            f"🧪 <b>Prompt draft — {prompt_name}: gate passed but couldn't publish</b>\n"
            f"Langfuse isn't configured on this deployment, so no `candidate` version "
            f"could be created. Gate report: {state.get('gate_summary')}"
        )
        return {"status": "publish_failed"}

    try:
        created = client.create_prompt(
            name=prompt_name,
            prompt=state["draft_text"],
            labels=["candidate"],
            type="text",
            commit_message=f"path-back leg 3e auto-draft: {state['trigger_reason']}",
        )
        candidate_version = created.version
    except Exception:
        logger.exception("prompt_drafter[%s]: create_prompt failed", prompt_name)
        telegram_bot.send_admin_alert(
            f"🧪 <b>Prompt draft — {prompt_name}: gate passed but publish failed</b>\n"
            f"Langfuse create_prompt raised — check Render logs. Gate report: "
            f"{state.get('gate_summary')}"
        )
        return {"status": "publish_failed"}

    # gate_summary is always the full _serialize_gate_report() dict here —
    # this node is only ever reached via the IMPROVED branch of
    # _route_after_gate, which always comes from a real GateReport (the
    # reason-only {"reason": ...} shape _run_gate can also return only ever
    # produces verdict="NO_CHANGE", which routes to report_no_change instead).
    gate_summary = state.get("gate_summary") or {}
    overall_delta = gate_summary.get("overall_delta")
    delta_str = f"{overall_delta:+.0%}" if isinstance(overall_delta, (int, float)) else "n/a"
    message = (
        f"✅ <b>Prompt candidate ready for review — {prompt_name} v{candidate_version}</b>\n"
        f"Trigger: {state['trigger_reason']}\n"
        f"Gate: baseline {gate_summary.get('baseline_overall_pass_rate')} -> "
        f"candidate {gate_summary.get('candidate_overall_pass_rate')} ({delta_str})\n"
        f"<i>To promote: open Langfuse → {prompt_name} → v{candidate_version} → "
        f"relabel to `production`. Nothing here does that automatically — see AGENTS.md "
        f"rule 8. This run is now paused waiting for that.</i>"
    )
    telegram_bot.send_admin_alert(message)
    logger.info("prompt_drafter[%s]: published candidate v%s", prompt_name, candidate_version)
    return {"status": "awaiting_approval", "candidate_version": candidate_version}


def _await_approval(state: DraftState) -> dict:
    # IMPORTANT: on resume, LangGraph re-runs this node's body from the top.
    # Everything before `interrupt()` returning must therefore be side-
    # effect-free (it re-executes); everything after it runs exactly once,
    # since the node completes normally the moment interrupt() returns a
    # resume value. All notification side effects below live after that
    # line for exactly this reason.
    from langgraph.types import interrupt

    result = interrupt({
        "prompt_name": state["prompt_name"],
        "candidate_version": state.get("candidate_version"),
        "gate_summary": state.get("gate_summary"),
    })
    logger.info(
        "prompt_drafter[%s]: resumed after approval — %s", state["prompt_name"], result,
    )
    telegram_bot.send_admin_alert(
        f"🎉 <b>Prompt promoted — {state['prompt_name']} v{state.get('candidate_version')}</b>\n"
        f"Confirmed live in Langfuse `production`. Path-back loop closed for this run."
    )
    return {"status": "promoted", "approval_result": result}


def _build_graph() -> StateGraph:
    from langgraph.graph import END, START, StateGraph

    g = StateGraph(DraftState)
    g.add_node("load_baseline", _load_baseline)
    g.add_node("draft_candidate", _draft_candidate)
    g.add_node("run_gate", _run_gate)
    g.add_node("publish_candidate", _publish_candidate)
    g.add_node("await_approval", _await_approval)
    g.add_node("report_blocked", _report_blocked)
    g.add_node("report_no_change", _report_no_change)

    g.add_edge(START, "load_baseline")
    g.add_edge("load_baseline", "draft_candidate")
    g.add_conditional_edges(
        "draft_candidate", _route_after_draft,
        {"run_gate": "run_gate", "blocked": "report_blocked"},
    )
    g.add_conditional_edges(
        "run_gate", _route_after_gate,
        {"publish_candidate": "publish_candidate", "blocked": "report_blocked", "no_change": "report_no_change"},
    )
    g.add_edge("publish_candidate", "await_approval")
    g.add_edge("report_blocked", END)
    g.add_edge("report_no_change", END)
    g.add_edge("await_approval", END)
    return g


# ---------------------------------------------------------------------------
# Checkpoint snapshot/restore — see module docstring's "PERSISTENCE" section.
# ---------------------------------------------------------------------------
def _dump_thread_state(saver: InMemorySaver, thread_id: str) -> str:
    payload = {
        "storage": dict(saver.storage.get(thread_id, {})),
        "writes": {k: v for k, v in saver.writes.items() if k[0] == thread_id},
        "blobs": {k: v for k, v in saver.blobs.items() if k[0] == thread_id},
    }
    return base64.b64encode(pickle.dumps(payload)).decode("ascii")


def _load_thread_state(saver: InMemorySaver, thread_id: str, blob_b64: str) -> None:
    payload = pickle.loads(base64.b64decode(blob_b64))
    saver.storage[thread_id] = payload["storage"]
    for k, v in payload["writes"].items():
        saver.writes[k] = v
    for k, v in payload["blobs"].items():
        saver.blobs[k] = v


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------
def start_draft_run(prompt_name: str, trigger_reason: str) -> dict:
    """Kick off a new draft-test-(maybe)publish run for `prompt_name`. Runs
    synchronously through load_baseline -> draft_candidate -> run_gate ->
    (blocked | no_change | publish_candidate -> await_approval). Never
    raises — any unexpected failure is caught and reported as
    status="error".
    """
    thread_id = str(uuid.uuid4())
    try:
        from langgraph.checkpoint.memory import InMemorySaver

        saver = InMemorySaver()
        graph = _build_graph().compile(checkpointer=saver)
        config = {"configurable": {"thread_id": thread_id}}
        result = graph.invoke(
            {"prompt_name": prompt_name, "trigger_reason": trigger_reason},
            config=config,
        )
    except Exception as e:
        logger.exception("prompt_drafter: start_draft_run failed for %s", prompt_name)
        return {"thread_id": thread_id, "prompt_name": prompt_name, "status": "error", "reason": str(e)}

    interrupted = bool(result.get("__interrupt__"))
    status = result.get("status") or ("awaiting_approval" if interrupted else "unknown")

    prompt_draft_store.create_run(
        thread_id, prompt_name, trigger_reason, status=status,
        baseline_version=result.get("baseline_version"),
        candidate_version=result.get("candidate_version"),
        gate_verdict=result.get("verdict"),
    )
    if interrupted:
        prompt_draft_store.save_checkpoint(thread_id, _dump_thread_state(saver, thread_id))

    return {
        "thread_id": thread_id, "prompt_name": prompt_name, "status": status,
        "verdict": result.get("verdict"), "candidate_version": result.get("candidate_version"),
    }


def resume_approved_run(thread_id: str, resume_value: dict) -> dict:
    """Resume a specific awaiting-approval run with a confirmed resume
    payload. Rehydrates the checkpointed thread state from
    prompt_draft_store, resumes via Command(resume=...), and persists the
    final status. Never raises.
    """
    blob = prompt_draft_store.load_checkpoint(thread_id)
    if not blob:
        logger.warning("prompt_drafter: resume_approved_run — no checkpoint for %s", thread_id)
        return {"thread_id": thread_id, "status": "error", "reason": "no checkpoint found"}

    try:
        from langgraph.checkpoint.memory import InMemorySaver
        from langgraph.types import Command

        saver = InMemorySaver()
        _load_thread_state(saver, thread_id, blob)
        graph = _build_graph().compile(checkpointer=saver)
        config = {"configurable": {"thread_id": thread_id}}
        result = graph.invoke(Command(resume=resume_value), config=config)
    except Exception as e:
        logger.exception("prompt_drafter: resume_approved_run failed for %s", thread_id)
        return {"thread_id": thread_id, "status": "error", "reason": str(e)}

    status = result.get("status", "promoted")
    prompt_draft_store.update_run(thread_id, status=status)
    return {"thread_id": thread_id, "status": status}


def check_pending_approvals() -> dict:
    """Daily job: for every run awaiting approval, check whether a human has
    already moved the Langfuse `production` label to that run's candidate
    version — if so, resume the graph (which logs + sends the closing
    confirmation) and mark it promoted. Otherwise leave it alone, unless
    it's been waiting past STALE_AFTER_DAYS, in which case mark it expired.
    Never raises.
    """
    summary = {"checked": 0, "promoted": 0, "still_waiting": 0, "expired": 0, "errors": 0}
    try:
        runs = prompt_draft_store.pending_approval_runs()
    except Exception:
        logger.exception("prompt_drafter: check_pending_approvals fetch failed")
        summary["errors"] += 1
        return summary

    now = datetime.now(timezone.utc)
    for run in runs:
        summary["checked"] += 1
        thread_id = run.get("thread_id")
        prompt_name = run.get("prompt_name")
        candidate_version = run.get("candidate_version")
        try:
            live = prompt_registry.get_prompt(prompt_name, "")
            if live.version is not None and candidate_version is not None and live.version == candidate_version:
                res = resume_approved_run(thread_id, {
                    "approved": True, "confirmed_production_version": live.version,
                    "confirmed_at": now.isoformat(),
                })
                if res.get("status") == "error":
                    summary["errors"] += 1
                else:
                    summary["promoted"] += 1
                continue

            created_at = run.get("created_at")
            if created_at:
                try:
                    created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    stale = (now - created_dt).days >= STALE_AFTER_DAYS
                except Exception:
                    stale = False
            else:
                stale = False

            if stale:
                prompt_draft_store.update_run(thread_id, status="expired")
                summary["expired"] += 1
            else:
                summary["still_waiting"] += 1
        except Exception:
            logger.exception("prompt_drafter: check_pending_approvals failed for run %s", thread_id)
            summary["errors"] += 1

    logger.info("prompt_drafter: check_pending_approvals complete — %s", summary)
    return summary


def run_pending_drafts(alert_lookback_days: int = ALERT_LOOKBACK_DAYS) -> dict:
    """Daily job: scan accuracy_monitor.py's alert log for recently flagged
    prompts and start a draft-test-approve run for each one that isn't
    already covered by an active run (see prompt_draft_store.
    active_run_for_prompt). Never raises.
    """
    summary = {
        "alerts_scanned": 0, "runs_started": 0,
        "skipped_active_run": 0, "skipped_unmonitored": 0, "errors": 0,
    }
    try:
        alerts = outcome_ledger.recent_accuracy_alerts(days=alert_lookback_days)
    except Exception:
        logger.exception("prompt_drafter: run_pending_drafts alert fetch failed")
        summary["errors"] += 1
        return summary

    seen_prompts: set[str] = set()
    for alert in alerts:
        summary["alerts_scanned"] += 1
        prompt_name = alert.get("prompt_name")
        if not prompt_name or prompt_name in seen_prompts:
            continue
        seen_prompts.add(prompt_name)

        if prompt_name not in accuracy_monitor.SOURCE_TO_PROMPT.values():
            summary["skipped_unmonitored"] += 1
            continue

        try:
            active = prompt_draft_store.active_run_for_prompt(prompt_name, days=DRAFT_RETRY_COOLDOWN_DAYS)
        except Exception:
            logger.exception("prompt_drafter: active_run_for_prompt failed for %s", prompt_name)
            active = None
        if active:
            summary["skipped_active_run"] += 1
            continue

        reason = f"accuracy_monitor alert ({alert.get('drop_pp')}pp drop): {alert.get('message') or 'no message'}"
        try:
            start_draft_run(prompt_name, reason)
            summary["runs_started"] += 1
        except Exception:
            logger.exception("prompt_drafter: start_draft_run failed for %s", prompt_name)
            summary["errors"] += 1

    logger.info("prompt_drafter: run_pending_drafts complete — %s", summary)
    return summary
