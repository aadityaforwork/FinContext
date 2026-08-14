"""
Deterministic tests for prompt_gate.py — no API key required.
app.services.ai_client.generate_grounded_json is monkeypatched (same
mechanism as test_eval_runner.py) so run_case's LLM calls are simulated
deterministically per (prompt_text, case) pair.
"""

from __future__ import annotations

from app.services import ai_client, eval_runner, prompt_gate


def _case(id_, check, holdout=False):
    return eval_runner.EvalCase(
        id=id_, prompt_name="test.prompt", context={"case": id_},
        schema_description="{}", check=check, holdout=holdout,
    )


def _scripted(responses_by_prompt_text: dict[str, list[dict]]):
    """Return a fake generate_grounded_json that yields the next item off a
    per-prompt-text queue on every call — lets a test script exactly which
    rep passes/fails for baseline vs candidate without touching a network."""
    cursors = {k: iter(v) for k, v in responses_by_prompt_text.items()}

    def _fn(**kw):
        return next(cursors[kw["task"]])

    return _fn


def test_identical_prompt_text_is_never_blocked_and_never_improved(monkeypatch):
    """Self-comparison (same text on both sides) with a deterministic
    always-pass check must show zero delta -- NO_CHANGE, not IMPROVED
    (delta 0 doesn't clear MIN_OVERALL_IMPROVEMENT) and not BLOCK."""
    monkeypatch.setattr(ai_client, "generate_grounded_json", lambda **kw: {"ok": True})
    case = _case("c1", lambda r: r.get("ok") is True)
    report = prompt_gate.compare([case], "SAME TEXT", "SAME TEXT", n=5)
    assert report.overall_delta == 0.0
    assert report.verdict == prompt_gate.Verdict.NO_CHANGE
    assert report.blocked_cases == []


def test_meaningful_case_regression_blocks_regardless_of_overall(monkeypatch):
    """One case craters, others improve a lot -- BLOCK must win even though
    the naive overall average would look like an improvement."""
    monkeypatch.setattr(ai_client, "generate_grounded_json", _scripted({
        "BASELINE": [{"ok": True}] * 5 + [{"ok": True}] * 5,   # both cases 5/5 at baseline
        "CANDIDATE": [{"ok": True}] * 5 + [{"ok": False}] * 5,  # good_case stays 5/5, bad_case craters to 0/5
    }))
    good_case = _case("good_case", lambda r: r.get("ok") is True)
    bad_case = _case("bad_case", lambda r: r.get("ok") is True)
    report = prompt_gate.compare([good_case, bad_case], "BASELINE", "CANDIDATE", n=5)
    assert "bad_case" in report.blocked_cases
    assert report.verdict == prompt_gate.Verdict.BLOCK


def test_overall_improvement_above_threshold_is_improved(monkeypatch):
    monkeypatch.setattr(ai_client, "generate_grounded_json", _scripted({
        "BASELINE": [{"ok": False}] * 5,   # 0/5
        "CANDIDATE": [{"ok": True}] * 5,   # 5/5 -- +100%, well above MIN_OVERALL_IMPROVEMENT
    }))
    case = _case("c1", lambda r: r.get("ok") is True)
    report = prompt_gate.compare([case], "BASELINE", "CANDIDATE", n=5)
    assert report.overall_delta == 1.0
    assert report.verdict == prompt_gate.Verdict.IMPROVED
    assert report.blocked_cases == []


def test_small_improvement_below_threshold_is_no_change_never_improved(monkeypatch):
    """A tiny positive delta must NOT count as IMPROVED -- 'anything smaller
    [than the minimum] is NO CHANGE, never an improvement.'"""
    monkeypatch.setattr(ai_client, "generate_grounded_json", _scripted({
        "BASELINE": [{"ok": True}, {"ok": True}, {"ok": True}, {"ok": True}, {"ok": False}],   # 4/5 = 0.8
        "CANDIDATE": [{"ok": True}] * 5,   # 5/5 = 1.0, delta = +0.2
    }))
    case = _case("c1", lambda r: r.get("ok") is True)
    report = prompt_gate.compare(
        [case], "BASELINE", "CANDIDATE", n=5,
        min_overall_improvement=0.5,  # +0.2 must not clear this
    )
    assert report.overall_delta == 0.2
    assert report.verdict == prompt_gate.Verdict.NO_CHANGE


def test_holdout_case_excluded_by_default(monkeypatch):
    monkeypatch.setattr(ai_client, "generate_grounded_json", lambda **kw: {"ok": True})
    visible = _case("visible", lambda r: True)
    hidden = _case("hidden", lambda r: True, holdout=True)
    report = prompt_gate.compare([visible, hidden], "BASELINE", "CANDIDATE", n=2)
    assert [c.case_id for c in report.comparisons] == ["visible"]
    assert report.holdout_excluded == ["hidden"]


def test_holdout_case_included_when_requested(monkeypatch):
    monkeypatch.setattr(ai_client, "generate_grounded_json", lambda **kw: {"ok": True})
    visible = _case("visible", lambda r: True)
    hidden = _case("hidden", lambda r: True, holdout=True)
    report = prompt_gate.compare([visible, hidden], "BASELINE", "CANDIDATE", n=2, include_holdout=True)
    assert {c.case_id for c in report.comparisons} == {"visible", "hidden"}
    assert report.holdout_excluded == []


def test_empty_active_case_set_is_a_noop_not_a_crash(monkeypatch):
    monkeypatch.setattr(ai_client, "generate_grounded_json", lambda **kw: {"ok": True})
    hidden = _case("hidden", lambda r: True, holdout=True)
    report = prompt_gate.compare([hidden], "BASELINE", "CANDIDATE", n=2)  # holdout excluded -> nothing active
    assert report.comparisons == []
    assert report.verdict == prompt_gate.Verdict.NO_CHANGE
    assert report.baseline_overall_pass_rate == 0.0


def test_gate_never_writes_or_promotes_anything():
    """Static guard: this module must never actually CALL the Langfuse
    label-writing API -- the docstring is allowed to mention
    `update_prompt`/`create_prompt` by name (explaining why the
    module doesn't call them), but no `.update_prompt(` /
    `.create_prompt(` call site may exist in the source."""
    import inspect

    src = inspect.getsource(prompt_gate)
    assert ".update_prompt(" not in src
    assert ".create_prompt(" not in src


def test_render_report_never_raises_and_mentions_human_action(monkeypatch):
    monkeypatch.setattr(ai_client, "generate_grounded_json", lambda **kw: {"ok": True})
    case = _case("c1", lambda r: True)
    report = prompt_gate.compare([case], "A", "B", n=2)
    text = prompt_gate.render_report(report)
    assert "VERDICT" in text
    assert "human action" in text
