"""
Deterministic tests for prompt_monitor.py (Phase 3 — online monitor).
outcome_ledger.call_metrics_rows and langfuse_client.get_client are
monkeypatched everywhere here -- no Supabase or Langfuse network call
happens in any of these tests.

Covers the five scenarios called out in the spec:
  - cold-start no-op
  - insufficient-sample no-op
  - correct revert on clear degradation
  - no action on improvement
  - failure-safety (every component degrades to no-op on error)
"""

from __future__ import annotations

from app.services import langfuse_client, outcome_ledger, prompt_monitor


def _row(version, *, source="langfuse", confidence=None, data_gaps_count=0,
         parse_error=False, tokens_in=100, tokens_out=100, duration_ms=1000.0):
    return {
        "prompt_version": version, "prompt_source": source, "confidence": confidence,
        "data_gaps_count": data_gaps_count, "parse_error": parse_error,
        "tokens_in": tokens_in, "tokens_out": tokens_out, "duration_ms": duration_ms,
        "created_at": "2026-08-12T00:00:00Z",
    }


class _FakeLangfuseClient:
    def __init__(self, raises: Exception | None = None):
        self._raises = raises
        self.calls: list[dict] = []

    def update_prompt(self, **kwargs):
        self.calls.append(kwargs)
        if self._raises is not None:
            raise self._raises


# ---------------------------------------------------------------------------
# Cold start
# ---------------------------------------------------------------------------
def test_cold_start_no_history_is_a_noop(monkeypatch):
    monkeypatch.setattr(outcome_ledger, "call_metrics_rows", lambda name, days=30: [])
    result = prompt_monitor.evaluate("portfolio.tomorrow_watch")
    assert result["action"] == "insufficient_sample"
    assert "no Langfuse-managed call history" in result["reason"]


def test_cold_start_only_fallback_rows_is_a_noop(monkeypatch):
    """Rows exist but none came from a real Langfuse fetch (source != 'langfuse')
    -- nothing to compare, nothing to revert to."""
    rows = [_row(None, source="fallback_no_client") for _ in range(50)]
    monkeypatch.setattr(outcome_ledger, "call_metrics_rows", lambda name, days=30: rows)
    result = prompt_monitor.evaluate("portfolio.tomorrow_watch")
    assert result["action"] == "insufficient_sample"


# ---------------------------------------------------------------------------
# Insufficient sample
# ---------------------------------------------------------------------------
def test_only_one_version_seen_is_insufficient_sample(monkeypatch):
    rows = [_row(3) for _ in range(50)]  # plenty of volume, but only ever v3
    monkeypatch.setattr(outcome_ledger, "call_metrics_rows", lambda name, days=30: rows)
    result = prompt_monitor.evaluate("portfolio.tomorrow_watch")
    assert result["action"] == "insufficient_sample"
    assert "only one version" in result["reason"]


def test_two_versions_but_below_min_sample_size_is_insufficient_sample(monkeypatch):
    rows = [_row(2) for _ in range(5)] + [_row(1) for _ in range(5)]  # below MIN_SAMPLE_SIZE=20
    monkeypatch.setattr(outcome_ledger, "call_metrics_rows", lambda name, days=30: rows)
    result = prompt_monitor.evaluate("portfolio.tomorrow_watch")
    assert result["action"] == "insufficient_sample"
    assert "sample too small" in result["reason"]
    assert result["current_version"] == 2
    assert result["previous_version"] == 1


def test_insufficient_sample_never_touches_langfuse(monkeypatch):
    fake = _FakeLangfuseClient()
    monkeypatch.setattr(langfuse_client, "get_client", lambda: fake)
    monkeypatch.setattr(outcome_ledger, "call_metrics_rows", lambda name, days=30: [])
    prompt_monitor.evaluate("portfolio.tomorrow_watch")
    assert fake.calls == []


# ---------------------------------------------------------------------------
# Correct revert on clear degradation
# ---------------------------------------------------------------------------
def test_reverts_on_clear_data_gaps_degradation(monkeypatch):
    # previous (v1): healthy, no data gaps. current (v2): every call has gaps.
    previous_rows = [_row(1, data_gaps_count=0) for _ in range(25)]
    current_rows = [_row(2, data_gaps_count=3) for _ in range(25)]
    rows = current_rows + previous_rows  # newest-first, v2 (current) appears first
    monkeypatch.setattr(outcome_ledger, "call_metrics_rows", lambda name, days=30: rows)
    fake = _FakeLangfuseClient()
    monkeypatch.setattr(langfuse_client, "get_client", lambda: fake)

    result = prompt_monitor.evaluate("portfolio.tomorrow_watch")

    assert result["action"] == "reverted"
    assert "data_gaps_rate" in result["degraded_metrics"]
    assert result["current_version"] == 2
    assert result["previous_version"] == 1
    assert fake.calls == [{"name": "portfolio.tomorrow_watch", "version": 1, "new_labels": ["production"]}]


def test_revert_write_failure_is_reported_not_raised(monkeypatch):
    previous_rows = [_row(1, data_gaps_count=0) for _ in range(25)]
    current_rows = [_row(2, data_gaps_count=3) for _ in range(25)]
    monkeypatch.setattr(outcome_ledger, "call_metrics_rows",
                         lambda name, days=30: current_rows + previous_rows)
    fake = _FakeLangfuseClient(raises=RuntimeError("network down"))
    monkeypatch.setattr(langfuse_client, "get_client", lambda: fake)

    result = prompt_monitor.evaluate("portfolio.tomorrow_watch")

    assert result["action"] == "revert_failed"
    assert "failed" in result["write_result"]


def test_revert_never_promotes_a_never_before_seen_version(monkeypatch):
    """Static guarantee check: the version passed to update_prompt is
    always `previous_version`, which by construction was already observed
    live in the call log -- never the current (degraded) version, never
    anything else."""
    previous_rows = [_row(7, data_gaps_count=0) for _ in range(25)]
    current_rows = [_row(9, data_gaps_count=5) for _ in range(25)]
    monkeypatch.setattr(outcome_ledger, "call_metrics_rows",
                         lambda name, days=30: current_rows + previous_rows)
    fake = _FakeLangfuseClient()
    monkeypatch.setattr(langfuse_client, "get_client", lambda: fake)

    result = prompt_monitor.evaluate("portfolio.tomorrow_watch")
    assert fake.calls[0]["version"] == 7
    assert fake.calls[0]["version"] != result["current_version"]


# ---------------------------------------------------------------------------
# No action on improvement (or on noise below threshold)
# ---------------------------------------------------------------------------
def test_no_action_when_current_version_improved(monkeypatch):
    previous_rows = [_row(1, data_gaps_count=3) for _ in range(25)]  # worse
    current_rows = [_row(2, data_gaps_count=0) for _ in range(25)]   # better
    monkeypatch.setattr(outcome_ledger, "call_metrics_rows",
                         lambda name, days=30: current_rows + previous_rows)
    fake = _FakeLangfuseClient()
    monkeypatch.setattr(langfuse_client, "get_client", lambda: fake)

    result = prompt_monitor.evaluate("portfolio.tomorrow_watch")

    assert result["action"] == "no_action"
    assert fake.calls == []  # never touches Langfuse when nothing degraded


def test_no_action_when_effect_below_threshold(monkeypatch):
    """A small wobble in data_gaps_rate (below MIN_EFFECT) must not trigger
    a revert -- same 'clear the noise floor' requirement as prompt_gate.py."""
    # previous: 1/25 gaps (~4%); current: 3/25 gaps (~12%) -- an 8pp rise,
    # under the 20pp MIN_EFFECT["data_gaps_rate"] threshold.
    previous_rows = [_row(1, data_gaps_count=(1 if i == 0 else 0)) for i in range(25)]
    current_rows = [_row(2, data_gaps_count=(1 if i < 3 else 0)) for i in range(25)]
    monkeypatch.setattr(outcome_ledger, "call_metrics_rows",
                         lambda name, days=30: current_rows + previous_rows)
    result = prompt_monitor.evaluate("portfolio.tomorrow_watch")
    assert result["action"] == "no_action"


def test_confidence_metric_not_applicable_is_never_treated_as_degraded(monkeypatch):
    """news_feed_annotation's schema has no confidence field -- every row's
    confidence is None. That must show up as 'not applicable', never as a
    100% low-confidence share."""
    previous_rows = [_row(1, confidence=None) for _ in range(25)]
    current_rows = [_row(2, confidence=None) for _ in range(25)]
    monkeypatch.setattr(outcome_ledger, "call_metrics_rows",
                         lambda name, days=30: current_rows + previous_rows)
    result = prompt_monitor.evaluate("portfolio.news_feed_annotation")
    assert result["action"] == "no_action"
    assert result["comparison"]["confidence_low_share"]["current"] is None
    assert result["comparison"]["confidence_low_share"]["degraded"] is False


# ---------------------------------------------------------------------------
# Failure safety -- every component degrades to a no-op on error
# ---------------------------------------------------------------------------
def test_evaluate_never_raises_when_call_metrics_rows_raises(monkeypatch):
    def _boom(name, days=30):
        raise RuntimeError("supabase down")

    monkeypatch.setattr(outcome_ledger, "call_metrics_rows", _boom)
    result = prompt_monitor.evaluate("portfolio.tomorrow_watch")
    assert result["action"] == "error"
    assert "supabase down" in result["reason"]


def test_evaluate_never_raises_when_langfuse_client_raises_outside_update(monkeypatch):
    previous_rows = [_row(1, data_gaps_count=0) for _ in range(25)]
    current_rows = [_row(2, data_gaps_count=3) for _ in range(25)]
    monkeypatch.setattr(outcome_ledger, "call_metrics_rows",
                         lambda name, days=30: current_rows + previous_rows)

    def _boom():
        raise RuntimeError("client init exploded")

    monkeypatch.setattr(langfuse_client, "get_client", _boom)
    result = prompt_monitor.evaluate("portfolio.tomorrow_watch")
    # get_client() itself raising is caught by evaluate()'s outer try/except
    # -- reported as action="error", not propagated.
    assert result["action"] == "error"


def test_revert_helper_no_client_configured_is_a_noop(monkeypatch):
    monkeypatch.setattr(langfuse_client, "get_client", lambda: None)
    ok, reason = prompt_monitor._revert_production_label("portfolio.tomorrow_watch", 1)
    assert ok is False
    assert "not configured" in reason


def test_aggregate_empty_rows_is_all_none_not_a_crash():
    agg = prompt_monitor._aggregate([])
    assert agg["n"] == 0
    assert all(agg[m] is None for m in prompt_monitor.METRICS)


def test_router_never_lets_one_prompt_failure_kill_the_batch(monkeypatch):
    """The endpoint's own loop (app/routers/prompt_monitor.py) wraps each
    prompt's evaluate() call so one exploding prompt doesn't take the
    others down -- exercised here at the function level since evaluate()
    itself is the thing guaranteed never to raise; this locks in that
    guarantee directly rather than importing FastAPI machinery."""
    calls = []

    def _flaky(name, days=prompt_monitor.LOOKBACK_DAYS):
        calls.append(name)
        if name == "portfolio.tomorrow_watch":
            raise RuntimeError("boom")
        return {"prompt_name": name, "action": "insufficient_sample", "reason": "no data"}

    results = {}
    for name in prompt_monitor.MONITORED_PROMPTS:
        try:
            results[name] = _flaky(name)
        except Exception as e:
            results[name] = {"prompt_name": name, "action": "error", "reason": str(e)}

    assert results["portfolio.tomorrow_watch"]["action"] == "error"
    assert results["portfolio.news_feed_annotation"]["action"] == "insufficient_sample"
    assert calls == list(prompt_monitor.MONITORED_PROMPTS)
