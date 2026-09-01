"""
Prompt-draft store — path-back leg 3e persistence layer
============================================================
Supabase read/write helpers for `prompt_draft_runs` + `prompt_draft_
checkpoints` (migration 011_prompt_drafter.sql), used by prompt_drafter.py.

Deliberately its OWN module rather than added to outcome_ledger.py, breaking
this session's own pattern of putting every Supabase helper there. Reason:
outcome_ledger.py's own docstring frames everything it owns as "a ledger of
AI-call telemetry" (predictions, outcomes, call metrics, alerts, miss
fixtures) — data ABOUT what the AI said and whether it was right. What lives
here is workflow-orchestration state for an agent (a run's lifecycle status,
an opaque LangGraph checkpoint blob) — a different kind of thing, not a
telemetry record, and outcome_ledger.py is already the biggest file in
services/. A second small, focused module beats bolting an unrelated
concern onto the first one just to keep the "one file" habit going.

Own Supabase client instance, same lazy-init/never-hard-fail pattern as
outcome_ledger.py (duplicated rather than imported — these two modules
should be able to evolve independently, and the init is 5 lines).

Public functions:
    create_run(thread_id, prompt_name, trigger_reason, *, trigger_type, status, ...)
    update_run(thread_id, **fields)
    get_run(thread_id) -> dict | None
    active_run_for_prompt(prompt_name, days) -> dict | None
    pending_approval_runs() -> list[dict]
    save_checkpoint(thread_id, blob_b64) -> bool
    load_checkpoint(thread_id) -> str | None

Every call is best-effort — never raises, degrades to a safe default (False
/ None / [] as appropriate) and logs, same posture as outcome_ledger.py.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

_client = None
if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    try:
        from supabase import create_client
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        logger.info("Supabase prompt_draft_store client initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client in prompt_draft_store: {e}")


def is_available() -> bool:
    return _client is not None


# ---------------------------------------------------------------------------
# prompt_draft_runs
# ---------------------------------------------------------------------------
def create_run(
    thread_id: str,
    prompt_name: str,
    trigger_reason: str,
    *,
    status: str,
    trigger_type: str = "accuracy",
    trigger_key: str | None = None,
    baseline_version: int | None = None,
    candidate_version: int | None = None,
    gate_verdict: str | None = None,
) -> bool:
    """Insert one new run row. Never raises; returns False on failure or if
    the client is unavailable."""
    if not _client:
        return False
    try:
        _client.table("prompt_draft_runs").insert({
            "thread_id": thread_id,
            "prompt_name": prompt_name,
            "trigger_reason": trigger_reason,
            "trigger_type": trigger_type,
            "trigger_key": trigger_key,
            "status": status,
            "baseline_version": baseline_version,
            "candidate_version": candidate_version,
            "gate_verdict": gate_verdict,
        }).execute()
        return True
    except Exception as e:
        logger.warning("prompt_draft_store.create_run failed: %s", e)
        return False


def update_run(thread_id: str, **fields) -> bool:
    """Patch an existing run row (status transitions, candidate_version once
    known, etc.). `updated_at` is always bumped. Never raises; returns False
    on failure or if the client is unavailable."""
    if not _client or not fields:
        return False
    try:
        payload = dict(fields)
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        _client.table("prompt_draft_runs").update(payload).eq("thread_id", thread_id).execute()
        return True
    except Exception as e:
        logger.warning("prompt_draft_store.update_run failed for %s: %s", thread_id, e)
        return False


def get_run(thread_id: str) -> dict | None:
    """One run row by thread_id, or None if missing/unavailable/failed.
    Never raises."""
    if not _client:
        return None
    try:
        rows = (
            _client.table("prompt_draft_runs")
            .select("*")
            .eq("thread_id", thread_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        return rows[0] if rows else None
    except Exception as e:
        logger.warning("prompt_draft_store.get_run failed for %s: %s", thread_id, e)
        return None


def active_run_for_prompt(prompt_name: str, days: int = 7) -> dict | None:
    """The most recent run for `prompt_name` that should block a NEW draft
    attempt from starting, or None if it's clear to proceed. Never raises.

    "Active" means either:
      - status == 'awaiting_approval' (ALWAYS blocks, any age) — a human
        hasn't decided on the last candidate yet; don't hand them a second
        one before they've acted on the first.
      - ANY status, created within the last `days` days — a cooldown so a
        still-degraded segment doesn't get a fresh draft attempt every
        single day the underlying accuracy alert keeps firing. Same
        "~1-2x the alert's own cooldown" reasoning as accuracy_monitor.py's
        ALERT_COOLDOWN_DAYS.
    """
    if not _client:
        return None
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        rows = (
            _client.table("prompt_draft_runs")
            .select("thread_id,status,created_at")
            .eq("prompt_name", prompt_name)
            .order("created_at", desc=True)
            .limit(5)
            .execute()
            .data
            or []
        )
    except Exception as e:
        logger.warning("prompt_draft_store.active_run_for_prompt failed for %s: %s", prompt_name, e)
        return None
    for r in rows:
        if r.get("status") == "awaiting_approval":
            return r
        if (r.get("created_at") or "") >= cutoff:
            return r
    return None


def pending_approval_runs() -> list[dict]:
    """Every run currently paused waiting on a human — the worklist for
    prompt_drafter.check_pending_approvals(). Never raises; [] on any
    failure or if the client is unavailable."""
    if not _client:
        return []
    try:
        rows = (
            _client.table("prompt_draft_runs")
            .select("thread_id,prompt_name,candidate_version,created_at")
            .eq("status", "awaiting_approval")
            .order("created_at")
            .limit(200)
            .execute()
            .data
            or []
        )
        return rows
    except Exception as e:
        logger.warning("prompt_draft_store.pending_approval_runs failed: %s", e)
        return []


# ---------------------------------------------------------------------------
# prompt_draft_checkpoints
# ---------------------------------------------------------------------------
def save_checkpoint(thread_id: str, blob_b64: str) -> bool:
    """Upsert the opaque LangGraph checkpoint blob for `thread_id`. Never
    raises; returns False on failure or if the client is unavailable."""
    if not _client:
        return False
    try:
        _client.table("prompt_draft_checkpoints").upsert({
            "thread_id": thread_id,
            "blob": blob_b64,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="thread_id").execute()
        return True
    except Exception as e:
        logger.warning("prompt_draft_store.save_checkpoint failed for %s: %s", thread_id, e)
        return False


def load_checkpoint(thread_id: str) -> str | None:
    """The stored blob for `thread_id`, or None if missing/unavailable/
    failed. Never raises."""
    if not _client:
        return None
    try:
        rows = (
            _client.table("prompt_draft_checkpoints")
            .select("blob")
            .eq("thread_id", thread_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        return rows[0]["blob"] if rows else None
    except Exception as e:
        logger.warning("prompt_draft_store.load_checkpoint failed for %s: %s", thread_id, e)
        return None
