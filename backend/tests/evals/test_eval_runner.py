"""
Deterministic tests for eval_runner.py — no API key required, no real LLM
call. `app.services.ai_client.generate_grounded_json` is monkeypatched
everywhere here so these run in CI on every push, same tier as
test_deterministic.py (kept as a separate file since it exercises a whole
module rather than a handful of functions alongside everything else there).
"""

from __future__ import annotations

from app.services import ai_client, eval_runner


def _case(check, **kw):
    return eval_runner.EvalCase(
        id=kw.pop("id", "case1"),
        prompt_name=kw.pop("prompt_name", "test.prompt"),
        context=kw.pop("context", {"x": 1}),
        schema_description=kw.pop("schema_description", "{}"),
        check=check,
        **kw,
    )


def test_run_case_counts_passes_across_n_reps(monkeypatch):
    monkeypatch.setattr(ai_client, "generate_grounded_json", lambda **kw: {"ok": True})
    case = _case(lambda r: r.get("ok") is True)
    result = eval_runner.run_case(case, "PROMPT TEXT", n=5)
    assert result.n == 5
    assert result.passes == 5
    assert result.pass_rate == 1.0
    assert result.errors == 0
    assert result.raw_results == [True] * 5


def test_run_case_reports_fractional_pass_rate_not_boolean(monkeypatch):
    calls = iter([{"ok": True}, {"ok": False}, {"ok": True}, {"ok": False}, {"ok": True}])
    monkeypatch.setattr(ai_client, "generate_grounded_json", lambda **kw: next(calls))
    case = _case(lambda r: r.get("ok") is True)
    result = eval_runner.run_case(case, "PROMPT TEXT", n=5)
    assert result.passes == 3
    assert result.pass_rate == 0.6  # not just True/False -- a real fraction


def test_run_case_default_n_is_five():
    assert eval_runner.DEFAULT_N == 5


def test_run_case_empty_or_falsy_result_counts_as_fail(monkeypatch):
    monkeypatch.setattr(ai_client, "generate_grounded_json", lambda **kw: {})
    case = _case(lambda r: True)  # check would pass if ever called
    result = eval_runner.run_case(case, "PROMPT TEXT", n=3)
    assert result.passes == 0
    assert result.errors == 0  # {} is a valid "unparseable" return, not an exception


def test_run_case_never_raises_on_llm_exception(monkeypatch):
    def _boom(**kw):
        raise RuntimeError("provider down")

    monkeypatch.setattr(ai_client, "generate_grounded_json", _boom)
    case = _case(lambda r: True)
    result = eval_runner.run_case(case, "PROMPT TEXT", n=4)
    assert result.passes == 0
    assert result.errors == 4
    assert result.n == 4


def test_run_case_never_raises_on_broken_check_function(monkeypatch):
    monkeypatch.setattr(ai_client, "generate_grounded_json", lambda **kw: {"ok": True})

    def _broken_check(r):
        raise ValueError("bug in the check itself")

    case = _case(_broken_check)
    result = eval_runner.run_case(case, "PROMPT TEXT", n=3)
    assert result.passes == 0
    assert result.errors == 3  # the check's own exception is caught by run_case's try/except


def test_run_cases_one_bad_case_does_not_abort_the_rest(monkeypatch):
    def _dispatch(**kw):
        if kw["context"].get("boom"):
            raise RuntimeError("this case's context triggers a provider error")
        return {"ok": True}

    monkeypatch.setattr(ai_client, "generate_grounded_json", _dispatch)
    good = _case(lambda r: r.get("ok") is True, id="good", context={"boom": False})
    bad = _case(lambda r: r.get("ok") is True, id="bad", context={"boom": True})
    results = eval_runner.run_cases([bad, good], "shared prompt text", n=2)
    assert results[0].case_id == "bad"
    assert results[0].passes == 0
    assert results[0].errors == 2
    assert results[1].case_id == "good"
    assert results[1].passes == 2


def test_summarize_reports_per_case_and_overall_pass_rate():
    results = [
        eval_runner.CaseResult(case_id="a", prompt_name="p", n=5, passes=5, errors=0, pass_rate=1.0),
        eval_runner.CaseResult(case_id="b", prompt_name="p", n=5, passes=2, errors=0, pass_rate=0.4),
    ]
    summary = eval_runner.summarize(results)
    assert summary["overall_pass_rate"] == 0.7
    assert summary["total_errors"] == 0
    assert {c["case_id"] for c in summary["cases"]} == {"a", "b"}


def test_summarize_empty_input_is_a_noop():
    summary = eval_runner.summarize([])
    assert summary["overall_pass_rate"] == 0.0
    assert summary["cases"] == []
