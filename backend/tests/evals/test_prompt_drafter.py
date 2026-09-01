"""
Deterministic tests for prompt_drafter.py (path-back leg 3e — draft / test /
approve agent). Every I/O boundary (ai_client, langfuse_client,
prompt_registry, prompt_gate, outcome_ledger, miss_fixtures, telegram_bot,
prompt_draft_store) is monkeypatched -- no Supabase/Langfuse/LLM network
call happens in any of these tests.

Covers: routing after draft/gate, publish-and-pause, checkpoint dump/load
roundtrip (the actual pause-across-requests mechanism), resume + promotion
confirmation, check_pending_approvals' three outcomes (promoted/still-
waiting/expired), run_pending_drafts' dedupe + cooldown + unmonitored-skip,
and failure-safety (every entry point degrades to a status/count, never
raises).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.services.llm import ai_client
from app.services.notify import telegram_bot
from app.services.observability import langfuse_client, prompt_registry
from app.services.outcomes import outcome_ledger
from app.services.pathback import (
    grounding_fixtures,
    miss_fixtures,
    prompt_draft_store,
    prompt_drafter,
    prompt_gate,
)
from app.services.pathback.eval_runner import CaseResult
from app.services.pathback.prompt_gate import CaseComparison, GateReport, Verdict


def _report(verdict: Verdict, *, overall_delta=0.2, blocked_cases=None) -> GateReport:
    cr = CaseResult(case_id="c1", prompt_name="portfolio.tomorrow_watch", n=5, passes=4, errors=0, pass_rate=0.8)
    comp = CaseComparison(
        case_id="c1", prompt_name="portfolio.tomorrow_watch",
        baseline=cr, candidate=cr, delta=overall_delta, blocked=bool(blocked_cases),
    )
    return GateReport(
        prompt_name="portfolio.tomorrow_watch", n=5,
        case_regression_block=0.34, min_overall_improvement=0.15,
        comparisons=[comp], holdout_excluded=[],
        baseline_overall_pass_rate=0.6, candidate_overall_pass_rate=0.6 + overall_delta,
        overall_delta=overall_delta, verdict=verdict, blocked_cases=blocked_cases or [],
    )


class _FakePromptResult:
    def __init__(self, text="BASELINE", version=3):
        self.text = text
        self.version = version
        self.source = "langfuse"


class _FakeCreated:
    def __init__(self, version):
        self.version = version


class _FakeLangfuseClient:
    def __init__(self, next_version=9, raises=None):
        self.next_version = next_version
        self.raises = raises
        self.calls = []

    def create_prompt(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises:
            raise self.raises
        return _FakeCreated(self.next_version)


@pytest.fixture(autouse=True)
def _common_mocks(monkeypatch):
    """Baseline happy-path plumbing shared by most tests: real baseline
    text, no miss-fixture cases, Telegram no-ops cleanly, nothing hits
    Supabase. Individual tests override what they need."""
    monkeypatch.setattr(prompt_registry, "get_prompt", lambda name, fb, **kw: _FakePromptResult())
    monkeypatch.setattr(outcome_ledger, "graded_misses", lambda horizon="1d", days=30: [])
    monkeypatch.setattr(outcome_ledger, "recent_grounding_alerts", lambda days=14: [])
    monkeypatch.setattr(miss_fixtures, "load_miss_fixture_cases", lambda prompt_name, limit=50: [])
    monkeypatch.setattr(grounding_fixtures, "load_grounding_fixture_cases", lambda prompt_name, limit=50: [])
    monkeypatch.setattr(grounding_fixtures, "build_drafting_evidence", lambda prompt_name, limit=8: "fixture")
    monkeypatch.setattr(telegram_bot, "send_admin_alert", lambda *a, **kw: True)
    monkeypatch.setattr(prompt_draft_store, "create_run", lambda *a, **kw: True)
    monkeypatch.setattr(prompt_draft_store, "update_run", lambda *a, **kw: True)
    monkeypatch.setattr(prompt_draft_store, "save_checkpoint", lambda *a, **kw: True)
    yield


# ---------------------------------------------------------------------------
# start_draft_run — routing outcomes
# ---------------------------------------------------------------------------
def test_start_draft_run_draft_generation_failure_routes_to_blocked(monkeypatch):
    monkeypatch.setattr(ai_client, "generate_text", lambda *a, **kw: "")
    result = prompt_drafter.start_draft_run("portfolio.tomorrow_watch", "test trigger")
    assert result["status"] == "blocked"


def test_start_draft_run_gate_block_verdict_never_publishes(monkeypatch):
    monkeypatch.setattr(ai_client, "generate_text", lambda *a, **kw: "REVISED PROMPT TEXT")
    monkeypatch.setattr(prompt_gate, "compare", lambda *a, **kw: _report(Verdict.BLOCK, blocked_cases=["c1"]))
    fake_lf = _FakeLangfuseClient()
    monkeypatch.setattr(langfuse_client, "get_client", lambda: fake_lf)

    result = prompt_drafter.start_draft_run("portfolio.tomorrow_watch", "test trigger")
    assert result["status"] == "blocked"
    assert result["verdict"] == "BLOCK"
    assert fake_lf.calls == []  # never published


def test_start_draft_run_no_change_verdict_never_publishes(monkeypatch):
    monkeypatch.setattr(ai_client, "generate_text", lambda *a, **kw: "REVISED PROMPT TEXT")
    monkeypatch.setattr(prompt_gate, "compare", lambda *a, **kw: _report(Verdict.NO_CHANGE, overall_delta=0.02))
    fake_lf = _FakeLangfuseClient()
    monkeypatch.setattr(langfuse_client, "get_client", lambda: fake_lf)

    result = prompt_drafter.start_draft_run("portfolio.tomorrow_watch", "test trigger")
    assert result["status"] == "no_change"
    assert fake_lf.calls == []


def test_start_draft_run_no_eval_cases_is_no_change_not_a_crash(monkeypatch):
    """prompt_eval_cases.ALL_CASES has nothing for an unmonitored prompt
    name and miss_fixtures returns [] too -- _run_gate's own empty-cases
    branch must produce NO_CHANGE, not an exception."""
    monkeypatch.setattr(ai_client, "generate_text", lambda *a, **kw: "REVISED PROMPT TEXT")
    result = prompt_drafter.start_draft_run("portfolio.nonexistent_prompt", "test trigger")
    assert result["status"] == "no_change"


def test_start_draft_run_improved_verdict_publishes_and_pauses(monkeypatch):
    monkeypatch.setattr(ai_client, "generate_text", lambda *a, **kw: "REVISED PROMPT TEXT")
    monkeypatch.setattr(prompt_gate, "compare", lambda *a, **kw: _report(Verdict.IMPROVED, overall_delta=0.3))
    fake_lf = _FakeLangfuseClient(next_version=11)
    monkeypatch.setattr(langfuse_client, "get_client", lambda: fake_lf)

    result = prompt_drafter.start_draft_run("portfolio.tomorrow_watch", "test trigger")
    assert result["status"] == "awaiting_approval"
    assert result["candidate_version"] == 11
    assert fake_lf.calls[0]["labels"] == ["candidate"]  # never 'production'
    assert fake_lf.calls[0]["name"] == "portfolio.tomorrow_watch"


def test_start_draft_run_publish_failure_when_langfuse_unconfigured(monkeypatch):
    monkeypatch.setattr(ai_client, "generate_text", lambda *a, **kw: "REVISED PROMPT TEXT")
    monkeypatch.setattr(prompt_gate, "compare", lambda *a, **kw: _report(Verdict.IMPROVED))
    monkeypatch.setattr(langfuse_client, "get_client", lambda: None)

    result = prompt_drafter.start_draft_run("portfolio.tomorrow_watch", "test trigger")
    assert result["status"] == "publish_failed"


def test_start_draft_run_publish_failure_when_create_prompt_raises(monkeypatch):
    monkeypatch.setattr(ai_client, "generate_text", lambda *a, **kw: "REVISED PROMPT TEXT")
    monkeypatch.setattr(prompt_gate, "compare", lambda *a, **kw: _report(Verdict.IMPROVED))
    monkeypatch.setattr(langfuse_client, "get_client", lambda: _FakeLangfuseClient(raises=RuntimeError("down")))

    result = prompt_drafter.start_draft_run("portfolio.tomorrow_watch", "test trigger")
    assert result["status"] == "publish_failed"


def test_start_draft_run_never_raises_on_draft_generation_exception(monkeypatch):
    def _boom(*a, **kw):
        raise RuntimeError("LLM down")
    monkeypatch.setattr(ai_client, "generate_text", _boom)
    result = prompt_drafter.start_draft_run("portfolio.tomorrow_watch", "test trigger")
    assert result["status"] == "blocked"


def test_start_draft_run_never_raises_on_totally_unexpected_failure(monkeypatch):
    def _boom(name, fb, **kw):
        raise RuntimeError("supabase down")
    monkeypatch.setattr(prompt_registry, "get_prompt", _boom)
    result = prompt_drafter.start_draft_run("portfolio.tomorrow_watch", "test trigger")
    assert result["status"] == "error"


# ---------------------------------------------------------------------------
# Checkpoint dump/load roundtrip + resume — the actual pause-across-requests
# mechanism. Exercises the REAL graph (only I/O boundaries mocked) end to
# end: run to the interrupt, snapshot into a blob, reload into a brand new
# InMemorySaver (simulating a separate process/request), resume via
# Command(resume=...), and confirm it completes correctly.
# ---------------------------------------------------------------------------
def test_full_run_pauses_and_resumes_via_checkpoint_roundtrip(monkeypatch):
    monkeypatch.setattr(ai_client, "generate_text", lambda *a, **kw: "REVISED PROMPT TEXT")
    monkeypatch.setattr(prompt_gate, "compare", lambda *a, **kw: _report(Verdict.IMPROVED))
    monkeypatch.setattr(langfuse_client, "get_client", lambda: _FakeLangfuseClient(next_version=7))

    captured_blob = {}

    def _save_checkpoint(thread_id, blob):
        captured_blob["thread_id"] = thread_id
        captured_blob["blob"] = blob
        return True
    monkeypatch.setattr(prompt_draft_store, "save_checkpoint", _save_checkpoint)

    start_result = prompt_drafter.start_draft_run("portfolio.tomorrow_watch", "test trigger")
    assert start_result["status"] == "awaiting_approval"
    assert captured_blob["thread_id"] == start_result["thread_id"]

    # Simulate a completely separate request: load_checkpoint returns the
    # blob captured above, nothing else about this test process is reused.
    monkeypatch.setattr(prompt_draft_store, "load_checkpoint", lambda tid: captured_blob["blob"])
    updated = {}
    monkeypatch.setattr(prompt_draft_store, "update_run", lambda tid, **kw: updated.update(kw) or True)

    resume_result = prompt_drafter.resume_approved_run(
        start_result["thread_id"], {"approved": True, "confirmed_production_version": 7},
    )
    assert resume_result["status"] == "promoted"
    assert updated["status"] == "promoted"


def test_resume_approved_run_missing_checkpoint_is_an_error_not_a_crash(monkeypatch):
    monkeypatch.setattr(prompt_draft_store, "load_checkpoint", lambda tid: None)
    result = prompt_drafter.resume_approved_run("nonexistent-thread", {"approved": True})
    assert result["status"] == "error"


def test_dump_and_load_thread_state_are_inverse_for_a_fresh_saver():
    """Direct unit check of the snapshot helpers themselves, independent of
    the full graph -- confirms round-tripping an empty/new thread doesn't
    blow up and produces a loadable blob."""
    saver = InMemorySaver()
    thread_id = "t1"
    # Nothing written yet -- dump should still succeed and produce something loadable.
    blob = prompt_drafter._dump_thread_state(saver, thread_id)
    assert isinstance(blob, str) and blob

    saver2 = InMemorySaver()
    prompt_drafter._load_thread_state(saver2, thread_id, blob)
    assert thread_id in saver2.storage


# ---------------------------------------------------------------------------
# check_pending_approvals
# ---------------------------------------------------------------------------
def test_check_pending_approvals_no_runs_is_a_clean_zero(monkeypatch):
    monkeypatch.setattr(prompt_draft_store, "pending_approval_runs", lambda: [])
    result = prompt_drafter.check_pending_approvals()
    assert result == {"checked": 0, "promoted": 0, "still_waiting": 0, "expired": 0, "errors": 0}


def test_check_pending_approvals_promotes_when_label_matches(monkeypatch):
    run = {"thread_id": "t1", "prompt_name": "portfolio.tomorrow_watch", "candidate_version": 5,
           "created_at": datetime.now(timezone.utc).isoformat()}
    monkeypatch.setattr(prompt_draft_store, "pending_approval_runs", lambda: [run])
    monkeypatch.setattr(prompt_registry, "get_prompt", lambda name, fb, **kw: _FakePromptResult(version=5))

    resumed = []
    monkeypatch.setattr(prompt_drafter, "resume_approved_run", lambda tid, val: resumed.append((tid, val)) or {"status": "promoted"})

    result = prompt_drafter.check_pending_approvals()
    assert result["promoted"] == 1
    assert result["still_waiting"] == 0
    assert resumed[0][0] == "t1"


def test_check_pending_approvals_still_waiting_when_label_unchanged(monkeypatch):
    run = {"thread_id": "t1", "prompt_name": "portfolio.tomorrow_watch", "candidate_version": 5,
           "created_at": datetime.now(timezone.utc).isoformat()}
    monkeypatch.setattr(prompt_draft_store, "pending_approval_runs", lambda: [run])
    # Live production is still v3, not the candidate v5 -- human hasn't acted yet.
    monkeypatch.setattr(prompt_registry, "get_prompt", lambda name, fb, **kw: _FakePromptResult(version=3))

    result = prompt_drafter.check_pending_approvals()
    assert result["still_waiting"] == 1
    assert result["promoted"] == 0


def test_check_pending_approvals_expires_stale_runs(monkeypatch):
    old = (datetime.now(timezone.utc) - timedelta(days=prompt_drafter.STALE_AFTER_DAYS + 1)).isoformat()
    run = {"thread_id": "t1", "prompt_name": "portfolio.tomorrow_watch", "candidate_version": 5, "created_at": old}
    monkeypatch.setattr(prompt_draft_store, "pending_approval_runs", lambda: [run])
    monkeypatch.setattr(prompt_registry, "get_prompt", lambda name, fb, **kw: _FakePromptResult(version=3))
    updated = {}
    monkeypatch.setattr(prompt_draft_store, "update_run", lambda tid, **kw: updated.update(kw) or True)

    result = prompt_drafter.check_pending_approvals()
    assert result["expired"] == 1
    assert updated["status"] == "expired"


def test_check_pending_approvals_never_raises_when_fetch_fails(monkeypatch):
    def _boom():
        raise RuntimeError("supabase down")
    monkeypatch.setattr(prompt_draft_store, "pending_approval_runs", _boom)
    result = prompt_drafter.check_pending_approvals()
    assert result["errors"] == 1


def test_check_pending_approvals_one_bad_run_does_not_abort_the_batch(monkeypatch):
    good = {"thread_id": "good", "prompt_name": "portfolio.tomorrow_watch", "candidate_version": 5,
            "created_at": datetime.now(timezone.utc).isoformat()}
    bad = {"thread_id": "bad", "prompt_name": "portfolio.news_feed_annotation", "candidate_version": 9,
           "created_at": datetime.now(timezone.utc).isoformat()}
    monkeypatch.setattr(prompt_draft_store, "pending_approval_runs", lambda: [bad, good])

    def _get_prompt(name, fb, **kw):
        if name == "portfolio.news_feed_annotation":
            raise RuntimeError("boom")
        return _FakePromptResult(version=5)
    monkeypatch.setattr(prompt_registry, "get_prompt", _get_prompt)
    monkeypatch.setattr(prompt_drafter, "resume_approved_run", lambda tid, val: {"status": "promoted"})

    result = prompt_drafter.check_pending_approvals()
    assert result["checked"] == 2
    assert result["promoted"] == 1
    assert result["errors"] == 1


# ---------------------------------------------------------------------------
# run_pending_drafts
# ---------------------------------------------------------------------------
def test_run_pending_drafts_no_alerts_is_a_clean_zero(monkeypatch):
    monkeypatch.setattr(outcome_ledger, "recent_accuracy_alerts", lambda days=14: [])
    result = prompt_drafter.run_pending_drafts()
    assert result["alerts_scanned"] == 0
    assert result["runs_started"] == 0


def test_run_pending_drafts_starts_a_run_for_a_flagged_prompt(monkeypatch):
    alert = {"source": "tomorrow_per_holding", "prompt_name": "portfolio.tomorrow_watch",
              "message": "drift", "drop_pp": 20.0}
    monkeypatch.setattr(outcome_ledger, "recent_accuracy_alerts", lambda days=14: [alert])
    monkeypatch.setattr(prompt_draft_store, "active_run_for_prompt", lambda name, days=7: None)
    started = []
    monkeypatch.setattr(prompt_drafter, "start_draft_run", lambda name, reason, **kw: started.append((name, reason)) or {})

    result = prompt_drafter.run_pending_drafts()
    assert result["runs_started"] == 1
    assert started[0][0] == "portfolio.tomorrow_watch"


def test_run_pending_drafts_skips_prompt_with_active_run(monkeypatch):
    alert = {"source": "tomorrow_per_holding", "prompt_name": "portfolio.tomorrow_watch",
              "message": "drift", "drop_pp": 20.0}
    monkeypatch.setattr(outcome_ledger, "recent_accuracy_alerts", lambda days=14: [alert])
    monkeypatch.setattr(prompt_draft_store, "active_run_for_prompt", lambda name, days=7: {"thread_id": "t1"})
    started = []
    monkeypatch.setattr(prompt_drafter, "start_draft_run", lambda name, reason, **kw: started.append(name) or {})

    result = prompt_drafter.run_pending_drafts()
    assert result["skipped_active_run"] == 1
    assert started == []


def test_run_pending_drafts_dedupes_multiple_alerts_for_same_prompt(monkeypatch):
    alerts = [
        {"source": "tomorrow_per_holding", "prompt_name": "portfolio.tomorrow_watch", "message": "a", "drop_pp": 20.0},
        {"source": "tomorrow_per_holding", "prompt_name": "portfolio.tomorrow_watch", "message": "b", "drop_pp": 18.0},
    ]
    monkeypatch.setattr(outcome_ledger, "recent_accuracy_alerts", lambda days=14: alerts)
    monkeypatch.setattr(prompt_draft_store, "active_run_for_prompt", lambda name, days=7: None)
    started = []
    monkeypatch.setattr(prompt_drafter, "start_draft_run", lambda name, reason, **kw: started.append(name) or {})

    result = prompt_drafter.run_pending_drafts()
    assert result["alerts_scanned"] == 2
    assert result["runs_started"] == 1
    assert started == ["portfolio.tomorrow_watch"]


def test_run_pending_drafts_skips_unmonitored_prompt_name(monkeypatch):
    alert = {"source": "weird", "prompt_name": "portfolio.something_else", "message": "x", "drop_pp": 20.0}
    monkeypatch.setattr(outcome_ledger, "recent_accuracy_alerts", lambda days=14: [alert])
    started = []
    monkeypatch.setattr(prompt_drafter, "start_draft_run", lambda name, reason, **kw: started.append(name) or {})

    result = prompt_drafter.run_pending_drafts()
    assert result["skipped_unmonitored"] == 1
    assert started == []


def test_run_pending_drafts_never_raises_when_alert_fetch_fails(monkeypatch):
    def _boom(days=14):
        raise RuntimeError("supabase down")
    monkeypatch.setattr(outcome_ledger, "recent_accuracy_alerts", _boom)
    result = prompt_drafter.run_pending_drafts()
    assert result["errors"] == 1


def test_run_pending_drafts_consumes_grounding_queue_with_explicit_tag(monkeypatch):
    alert = {
        "prompt_name": "portfolio.movers_attribution",
        "violation_type": "grounding.citation_validity",
        "failure_n": 8,
        "recent_n": 10,
        "failure_rate_pct": 80.0,
        "message": "bad paths",
    }
    monkeypatch.setattr(outcome_ledger, "recent_accuracy_alerts", lambda days=14: [])
    monkeypatch.setattr(outcome_ledger, "recent_grounding_alerts", lambda days=14: [alert])
    monkeypatch.setattr(prompt_draft_store, "active_run_for_prompt", lambda name, days=7: None)
    started = []
    monkeypatch.setattr(
        prompt_drafter, "start_draft_run",
        lambda name, reason, **kw: started.append((name, reason, kw)) or {},
    )

    result = prompt_drafter.run_pending_drafts()
    assert result["grounding_alerts_scanned"] == 1
    assert result["runs_started"] == 1
    assert started[0][0] == "portfolio.movers_attribution"
    assert started[0][2] == {
        "trigger_type": "grounding",
        "trigger_key": "grounding.citation_validity",
    }


def test_grounding_trigger_uses_grounding_specific_meta_prompt(monkeypatch):
    captured = []
    monkeypatch.setattr(
        ai_client, "generate_text",
        lambda prompt, **kw: captured.append(prompt) or "REVISED PROMPT",
    )
    state = {
        "prompt_name": "portfolio.movers_attribution",
        "trigger_reason": "citation validity failed",
        "trigger_type": "grounding",
        "baseline_text": "BASELINE",
        "evidence": "EXACT CONTEXT AND OUTPUT",
    }
    assert prompt_drafter._draft_candidate(state)["draft_text"] == "REVISED PROMPT"
    assert "Does NOT game".lower() in captured[0].lower()
    assert "EXACT CONTEXT AND OUTPUT" in captured[0]


# ---------------------------------------------------------------------------
# Non-negotiable: the module never writes a `production` label anywhere.
# ---------------------------------------------------------------------------
def test_module_never_calls_update_prompt():
    import inspect
    src = inspect.getsource(prompt_drafter)
    assert ".update_prompt(" not in src
    assert 'labels=["production"]' not in src
