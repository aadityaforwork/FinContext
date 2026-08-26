"""
Deterministic tests for miss_fixtures.py (path-back leg 3d — miss to
fixture converter). outcome_ledger.graded_misses/call_context/
log_miss_fixture/miss_fixture_rows are monkeypatched everywhere here -- no
Supabase network call happens in any of these tests.

Covers: no-history no-op, missing call_id / missing context skips,
correct conversion on a clean miss, the news_feed 'neutral' unrepresentable
case, idempotent re-conversion (already-exists skip), and failure-safety
(every component degrades to no-op on error).
"""

from __future__ import annotations

from app.services.outcomes import outcome_ledger
from app.services.pathback import miss_fixtures


def _miss(
    prediction_id="p1", ticker="TCS", source="tomorrow_per_holding",
    direction="positive", return_pct=-2.0, call_id="call-1", catalyst_type="earnings",
    reason="some claim",
):
    return {
        "prediction_id": prediction_id, "ticker": ticker,
        "prediction_date": "2026-08-10", "source": source,
        "catalyst_type": catalyst_type, "direction": direction,
        "reason": reason, "return_pct": return_pct,
        "metadata": {"call_id": call_id} if call_id else {},
    }


# ---------------------------------------------------------------------------
# _expected_direction -- deterministic, no LLM
# ---------------------------------------------------------------------------
# `horizon` is a required arg — the threshold scales with it. These cases use
# the module's own HORIZON so they keep testing the path production takes;
# the cross-horizon behavior itself is covered in test_hit_threshold.py.
def test_expected_direction_positive():
    assert miss_fixtures._expected_direction(2.0, miss_fixtures.HORIZON) == "positive"


def test_expected_direction_negative():
    assert miss_fixtures._expected_direction(-2.0, miss_fixtures.HORIZON) == "negative"


def test_expected_direction_neutral_inside_threshold():
    assert miss_fixtures._expected_direction(0.1, miss_fixtures.HORIZON) == "neutral"


# ---------------------------------------------------------------------------
# No history / cold start
# ---------------------------------------------------------------------------
def test_no_misses_is_a_clean_zero_summary(monkeypatch):
    monkeypatch.setattr(outcome_ledger, "graded_misses", lambda horizon="1d", days=30: [])
    result = miss_fixtures.convert_pending_misses()
    assert result["scanned"] == 0
    assert result["converted"] == 0
    assert result["errors"] == 0


# ---------------------------------------------------------------------------
# Skip reasons
# ---------------------------------------------------------------------------
def test_skips_unmonitored_source(monkeypatch):
    m = _miss(source="some_other_source")
    monkeypatch.setattr(outcome_ledger, "graded_misses", lambda horizon="1d", days=30: [m])
    result = miss_fixtures.convert_pending_misses()
    assert result["scanned"] == 1
    assert result["skipped_unmonitored_source"] == 1
    assert result["converted"] == 0


def test_skips_missing_call_id(monkeypatch):
    m = _miss(call_id=None)
    monkeypatch.setattr(outcome_ledger, "graded_misses", lambda horizon="1d", days=30: [m])
    called = []
    monkeypatch.setattr(outcome_ledger, "call_context", lambda cid: called.append(cid) or None)
    result = miss_fixtures.convert_pending_misses()
    assert result["skipped_no_call_id"] == 1
    assert called == []  # never even looked up context without a call_id


def test_skips_missing_context(monkeypatch):
    m = _miss()
    monkeypatch.setattr(outcome_ledger, "graded_misses", lambda horizon="1d", days=30: [m])
    monkeypatch.setattr(outcome_ledger, "call_context", lambda cid: {"context_snapshot": None})
    result = miss_fixtures.convert_pending_misses()
    assert result["skipped_no_context"] == 1


def test_news_feed_neutral_ground_truth_is_unrepresentable(monkeypatch):
    """news_feed_annotation's schema has no 'neutral' direction option --
    a miss whose market-graded truth is 'neutral' can't become a fixture
    for that prompt."""
    m = _miss(source="news_feed", direction="positive", return_pct=0.1)  # -> expected "neutral"
    monkeypatch.setattr(outcome_ledger, "graded_misses", lambda horizon="1d", days=30: [m])
    monkeypatch.setattr(outcome_ledger, "call_context", lambda cid: {"context_snapshot": {"x": 1}})
    written = []
    monkeypatch.setattr(outcome_ledger, "log_miss_fixture", lambda *a, **kw: written.append(1) or True)

    result = miss_fixtures.convert_pending_misses()
    assert result["skipped_unrepresentable_direction"] == 1
    assert written == []


def test_tomorrow_watch_neutral_ground_truth_is_representable(monkeypatch):
    """tomorrow_watch's schema DOES have 'neutral' -- same scenario as
    above must convert, not skip, for this source."""
    m = _miss(source="tomorrow_per_holding", direction="positive", return_pct=0.1)
    monkeypatch.setattr(outcome_ledger, "graded_misses", lambda horizon="1d", days=30: [m])
    monkeypatch.setattr(outcome_ledger, "call_context", lambda cid: {"context_snapshot": {"x": 1}})
    monkeypatch.setattr(outcome_ledger, "log_miss_fixture", lambda *a, **kw: True)

    result = miss_fixtures.convert_pending_misses()
    assert result["converted"] == 1
    assert result["skipped_unrepresentable_direction"] == 0


# ---------------------------------------------------------------------------
# Correct conversion
# ---------------------------------------------------------------------------
def test_converts_a_clean_miss(monkeypatch):
    m = _miss(
        prediction_id="pred-abc", ticker="TCS", source="tomorrow_per_holding",
        direction="positive", return_pct=-2.5, call_id="call-xyz",
    )
    monkeypatch.setattr(outcome_ledger, "graded_misses", lambda horizon="1d", days=30: [m])
    monkeypatch.setattr(
        outcome_ledger, "call_context",
        lambda cid: {"prompt_name": "portfolio.tomorrow_watch", "context_snapshot": {"holdings": []}},
    )
    captured = {}

    def _fake_log(prediction_id, prompt_name, **kw):
        captured["prediction_id"] = prediction_id
        captured["prompt_name"] = prompt_name
        captured.update(kw)
        return True

    monkeypatch.setattr(outcome_ledger, "log_miss_fixture", _fake_log)

    result = miss_fixtures.convert_pending_misses()

    assert result["converted"] == 1
    assert result["errors"] == 0
    assert captured["prediction_id"] == "pred-abc"
    assert captured["prompt_name"] == "portfolio.tomorrow_watch"
    assert captured["ticker"] == "TCS"
    assert captured["original_direction"] == "positive"
    assert captured["expected_direction"] == "negative"  # return_pct=-2.5
    assert captured["context_snapshot"] == {"holdings": []}


def test_already_converted_is_counted_not_an_error(monkeypatch):
    m = _miss()
    monkeypatch.setattr(outcome_ledger, "graded_misses", lambda horizon="1d", days=30: [m])
    monkeypatch.setattr(outcome_ledger, "call_context", lambda cid: {"context_snapshot": {"x": 1}})
    monkeypatch.setattr(outcome_ledger, "log_miss_fixture", lambda *a, **kw: False)  # duplicate key -> False

    result = miss_fixtures.convert_pending_misses()
    assert result["skipped_already_exists"] == 1
    assert result["converted"] == 0
    assert result["errors"] == 0


# ---------------------------------------------------------------------------
# Failure safety
# ---------------------------------------------------------------------------
def test_convert_pending_misses_never_raises_when_graded_misses_raises(monkeypatch):
    def _boom(horizon="1d", days=30):
        raise RuntimeError("supabase down")

    monkeypatch.setattr(outcome_ledger, "graded_misses", _boom)
    result = miss_fixtures.convert_pending_misses()
    assert result["errors"] == 1
    assert result["converted"] == 0


def test_one_bad_miss_does_not_abort_the_batch(monkeypatch):
    good = _miss(prediction_id="good", ticker="TCS")
    bad = _miss(prediction_id="bad", ticker="INFY", call_id="boom-id")
    monkeypatch.setattr(outcome_ledger, "graded_misses", lambda horizon="1d", days=30: [bad, good])

    def _call_context(cid):
        if cid == "boom-id":
            raise RuntimeError("network blip")
        return {"context_snapshot": {"x": 1}}

    monkeypatch.setattr(outcome_ledger, "call_context", _call_context)
    monkeypatch.setattr(outcome_ledger, "log_miss_fixture", lambda *a, **kw: True)

    result = miss_fixtures.convert_pending_misses()
    assert result["scanned"] == 2
    assert result["converted"] == 1  # the good one still went through
    assert result["errors"] == 1


def test_respects_limit(monkeypatch):
    misses = [_miss(prediction_id=f"p{i}", ticker=f"T{i}") for i in range(5)]
    monkeypatch.setattr(outcome_ledger, "graded_misses", lambda horizon="1d", days=30: misses)
    monkeypatch.setattr(outcome_ledger, "call_context", lambda cid: {"context_snapshot": {"x": 1}})
    monkeypatch.setattr(outcome_ledger, "log_miss_fixture", lambda *a, **kw: True)

    result = miss_fixtures.convert_pending_misses(limit=2)
    assert result["scanned"] == 2


# ---------------------------------------------------------------------------
# load_miss_fixture_cases
# ---------------------------------------------------------------------------
def test_load_miss_fixture_cases_builds_runnable_evalcases(monkeypatch):
    rows = [{
        "ticker": "TCS", "prediction_date": "2026-08-10",
        "expected_direction": "negative",
        "context_snapshot": {"holdings": [{"ticker": "TCS"}]},
    }]
    monkeypatch.setattr(outcome_ledger, "miss_fixture_rows", lambda prompt_name, limit=200: rows)

    cases = miss_fixtures.load_miss_fixture_cases("portfolio.tomorrow_watch")
    assert len(cases) == 1
    case = cases[0]
    assert case.prompt_name == "portfolio.tomorrow_watch"
    assert case.context == {"holdings": [{"ticker": "TCS"}]}

    # The check must pass when the model gets it right...
    assert case.check({"per_holding": [{"ticker": "TCS", "direction": "negative"}]}) is True
    # ...and fail when it repeats the original miss.
    assert case.check({"per_holding": [{"ticker": "TCS", "direction": "positive"}]}) is False
    # ...and fail (not raise) when the ticker is simply absent.
    assert case.check({"per_holding": []}) is False


def test_load_miss_fixture_cases_news_feed_checks_affected_tickers_list(monkeypatch):
    rows = [{
        "ticker": "HDFCBANK", "prediction_date": "2026-08-10",
        "expected_direction": "negative",
        "context_snapshot": {"user_holdings": ["HDFCBANK"]},
    }]
    monkeypatch.setattr(outcome_ledger, "miss_fixture_rows", lambda prompt_name, limit=200: rows)

    cases = miss_fixtures.load_miss_fixture_cases("portfolio.news_feed_annotation")
    assert len(cases) == 1
    check = cases[0].check
    assert check({"items": [{"affected_tickers": ["HDFCBANK", "ICICIBANK"], "direction": "negative"}]}) is True
    assert check({"items": [{"affected_tickers": ["ICICIBANK"], "direction": "negative"}]}) is False


def test_load_miss_fixture_cases_unknown_prompt_returns_empty(monkeypatch):
    assert miss_fixtures.load_miss_fixture_cases("some.other.prompt") == []


def test_load_miss_fixture_cases_never_raises_on_fetch_failure(monkeypatch):
    def _boom(prompt_name, limit=200):
        raise RuntimeError("supabase down")

    monkeypatch.setattr(outcome_ledger, "miss_fixture_rows", _boom)
    assert miss_fixtures.load_miss_fixture_cases("portfolio.tomorrow_watch") == []


def test_load_miss_fixture_cases_skips_rows_missing_required_fields(monkeypatch):
    rows = [
        {"ticker": "TCS", "prediction_date": "2026-08-10", "expected_direction": "negative",
         "context_snapshot": None},  # no context -- skip
        {"ticker": None, "prediction_date": "2026-08-10", "expected_direction": "negative",
         "context_snapshot": {"x": 1}},  # no ticker -- skip
    ]
    monkeypatch.setattr(outcome_ledger, "miss_fixture_rows", lambda prompt_name, limit=200: rows)
    assert miss_fixtures.load_miss_fixture_cases("portfolio.tomorrow_watch") == []
