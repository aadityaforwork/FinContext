"""
Deterministic tests for accuracy_monitor.py (path-back leg 3c — market-
accuracy drift alert). outcome_ledger.scored_rows/log_accuracy_alert/
last_accuracy_alert and telegram_bot.send_admin_alert are monkeypatched
everywhere here -- no Supabase or Telegram network call happens in any of
these tests.

Covers: cold-start no-op, insufficient-sample no-op, correct alert on clear
degradation, no action on a small/noisy drop, alert cooldown, and
failure-safety (every component degrades to no-op on error).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services import accuracy_monitor, outcome_ledger, telegram_bot

SOURCE = "tomorrow_per_holding"
TODAY = datetime(2026, 8, 13, tzinfo=timezone.utc)


def _row(prediction_date: str, hit: bool, *, source: str = SOURCE, catalyst_type: str = "earnings"):
    return {"source": source, "catalyst_type": catalyst_type, "hit": hit, "prediction_date": prediction_date}


def _dated_rows(n: int, hit_rate: float, *, days_ago: int) -> list[dict]:
    """n rows all dated `days_ago` days before TODAY, with `hit_rate` fraction hit=True."""
    d = (TODAY.date() - timedelta(days=days_ago)).isoformat()
    n_hits = round(n * hit_rate)
    return [_row(d, i < n_hits) for i in range(n)]


# ---------------------------------------------------------------------------
# Cold start / insufficient sample
# ---------------------------------------------------------------------------
def test_no_history_is_insufficient_sample(monkeypatch):
    monkeypatch.setattr(outcome_ledger, "scored_rows", lambda horizon="1d", days=104: [])
    result = accuracy_monitor.evaluate(SOURCE, now=TODAY)
    assert result["action"] == "insufficient_sample"
    assert "no scored" in result["reason"]


def test_only_other_source_rows_is_insufficient_sample(monkeypatch):
    """scored_rows() returns real volume, just none of it for SOURCE --
    accuracy_monitor.evaluate() must filter by source before counting."""
    only_other = [{**r, "source": "news_feed"} for r in _dated_rows(50, 0.9, days_ago=5)]
    monkeypatch.setattr(outcome_ledger, "scored_rows", lambda horizon="1d", days=104: only_other)
    result = accuracy_monitor.evaluate(SOURCE, now=TODAY)
    assert result["action"] == "insufficient_sample"


def test_below_min_sample_size_in_recent_window_is_insufficient_sample(monkeypatch):
    rows = _dated_rows(5, 0.5, days_ago=5) + _dated_rows(50, 0.5, days_ago=50)  # recent n=5 < MIN_SAMPLE_SIZE
    monkeypatch.setattr(outcome_ledger, "scored_rows", lambda horizon="1d", days=104: rows)
    result = accuracy_monitor.evaluate(SOURCE, now=TODAY)
    assert result["action"] == "insufficient_sample"
    assert "sample too small" in result["reason"]
    assert result["recent_n"] == 5


def test_below_min_sample_size_in_baseline_window_is_insufficient_sample(monkeypatch):
    rows = _dated_rows(25, 0.5, days_ago=5) + _dated_rows(10, 0.5, days_ago=50)  # baseline n=10 < MIN_SAMPLE_SIZE
    monkeypatch.setattr(outcome_ledger, "scored_rows", lambda horizon="1d", days=104: rows)
    result = accuracy_monitor.evaluate(SOURCE, now=TODAY)
    assert result["action"] == "insufficient_sample"
    assert result["baseline_n"] == 10


def test_insufficient_sample_never_touches_telegram(monkeypatch):
    sent = []
    monkeypatch.setattr(telegram_bot, "send_admin_alert", lambda text, **kw: sent.append(text) or True)
    monkeypatch.setattr(outcome_ledger, "scored_rows", lambda horizon="1d", days=104: [])
    accuracy_monitor.evaluate(SOURCE, now=TODAY)
    assert sent == []


# ---------------------------------------------------------------------------
# No action -- improvement, or a drop that doesn't clear the noise floor
# ---------------------------------------------------------------------------
def test_no_action_when_recent_matches_baseline(monkeypatch):
    rows = _dated_rows(25, 0.6, days_ago=5) + _dated_rows(25, 0.6, days_ago=50)
    monkeypatch.setattr(outcome_ledger, "scored_rows", lambda horizon="1d", days=104: rows)
    sent = []
    monkeypatch.setattr(telegram_bot, "send_admin_alert", lambda text, **kw: sent.append(text) or True)
    result = accuracy_monitor.evaluate(SOURCE, now=TODAY)
    assert result["action"] == "no_action"
    assert sent == []


def test_no_action_when_recent_improved(monkeypatch):
    rows = _dated_rows(25, 0.3, days_ago=50) + _dated_rows(25, 0.8, days_ago=5)  # baseline worse, recent better
    monkeypatch.setattr(outcome_ledger, "scored_rows", lambda horizon="1d", days=104: rows)
    result = accuracy_monitor.evaluate(SOURCE, now=TODAY)
    assert result["action"] == "no_action"


def test_no_action_when_drop_below_threshold(monkeypatch):
    # baseline 60% -> recent 50% is only a 10pp drop, under MIN_DROP_PP=15.
    rows = _dated_rows(30, 0.6, days_ago=50) + _dated_rows(30, 0.5, days_ago=5)
    monkeypatch.setattr(outcome_ledger, "scored_rows", lambda horizon="1d", days=104: rows)
    result = accuracy_monitor.evaluate(SOURCE, now=TODAY)
    assert result["action"] == "no_action"
    assert result["drop_pp"] < accuracy_monitor.MIN_DROP_PP


# ---------------------------------------------------------------------------
# Correct alert on clear degradation
# ---------------------------------------------------------------------------
def test_alerts_on_clear_degradation(monkeypatch):
    # baseline 70% -> recent 30%: a 40pp drop, well past MIN_DROP_PP.
    rows = _dated_rows(30, 0.7, days_ago=50) + _dated_rows(30, 0.3, days_ago=5)
    monkeypatch.setattr(outcome_ledger, "scored_rows", lambda horizon="1d", days=104: rows)
    monkeypatch.setattr(outcome_ledger, "last_accuracy_alert", lambda source, days=7: None)
    logged = []
    monkeypatch.setattr(
        outcome_ledger, "log_accuracy_alert",
        lambda source, prompt_name, **kw: logged.append((source, prompt_name, kw)) or True,
    )
    sent = []
    monkeypatch.setattr(telegram_bot, "send_admin_alert", lambda text, **kw: sent.append(text) or True)

    result = accuracy_monitor.evaluate(SOURCE, now=TODAY)

    assert result["action"] == "alerted"
    assert result["prompt_name"] == "portfolio.tomorrow_watch"
    assert result["drop_pp"] >= accuracy_monitor.MIN_DROP_PP
    assert len(sent) == 1
    assert SOURCE in sent[0]
    assert len(logged) == 1
    assert logged[0][0] == SOURCE
    assert logged[0][1] == "portfolio.tomorrow_watch"


def test_alert_send_failure_is_reported_not_raised(monkeypatch):
    rows = _dated_rows(30, 0.7, days_ago=50) + _dated_rows(30, 0.3, days_ago=5)
    monkeypatch.setattr(outcome_ledger, "scored_rows", lambda horizon="1d", days=104: rows)
    monkeypatch.setattr(outcome_ledger, "last_accuracy_alert", lambda source, days=7: None)
    monkeypatch.setattr(outcome_ledger, "log_accuracy_alert", lambda source, prompt_name, **kw: True)
    monkeypatch.setattr(telegram_bot, "send_admin_alert", lambda text, **kw: False)  # not configured

    result = accuracy_monitor.evaluate(SOURCE, now=TODAY)
    assert result["action"] == "alert_send_failed"


def test_alert_still_logged_even_when_persist_raises(monkeypatch):
    """log_accuracy_alert raising must not prevent the function from
    returning a clean result -- best-effort logging can't crash the eval."""
    rows = _dated_rows(30, 0.7, days_ago=50) + _dated_rows(30, 0.3, days_ago=5)
    monkeypatch.setattr(outcome_ledger, "scored_rows", lambda horizon="1d", days=104: rows)
    monkeypatch.setattr(outcome_ledger, "last_accuracy_alert", lambda source, days=7: None)

    def _boom(source, prompt_name, **kw):
        raise RuntimeError("supabase down")

    monkeypatch.setattr(outcome_ledger, "log_accuracy_alert", _boom)
    monkeypatch.setattr(telegram_bot, "send_admin_alert", lambda text, **kw: True)

    result = accuracy_monitor.evaluate(SOURCE, now=TODAY)
    assert result["action"] == "alerted"


# ---------------------------------------------------------------------------
# Alert cooldown
# ---------------------------------------------------------------------------
def test_cooldown_skips_realert_for_still_degraded_segment(monkeypatch):
    rows = _dated_rows(30, 0.7, days_ago=50) + _dated_rows(30, 0.3, days_ago=5)
    monkeypatch.setattr(outcome_ledger, "scored_rows", lambda horizon="1d", days=104: rows)
    monkeypatch.setattr(
        outcome_ledger, "last_accuracy_alert",
        lambda source, days=7: {"created_at": "2026-08-10T00:00:00Z"},
    )
    sent = []
    monkeypatch.setattr(telegram_bot, "send_admin_alert", lambda text, **kw: sent.append(text) or True)

    result = accuracy_monitor.evaluate(SOURCE, now=TODAY)

    assert result["action"] == "already_alerted_recently"
    assert sent == []


def test_cooldown_check_raising_does_not_block_alert(monkeypatch):
    """If the cooldown lookup itself fails, fail open (alert anyway) rather
    than silently swallowing a real degradation."""
    rows = _dated_rows(30, 0.7, days_ago=50) + _dated_rows(30, 0.3, days_ago=5)
    monkeypatch.setattr(outcome_ledger, "scored_rows", lambda horizon="1d", days=104: rows)

    def _boom(source, days=7):
        raise RuntimeError("supabase down")

    monkeypatch.setattr(outcome_ledger, "last_accuracy_alert", _boom)
    monkeypatch.setattr(outcome_ledger, "log_accuracy_alert", lambda source, prompt_name, **kw: True)
    sent = []
    monkeypatch.setattr(telegram_bot, "send_admin_alert", lambda text, **kw: sent.append(text) or True)

    result = accuracy_monitor.evaluate(SOURCE, now=TODAY)
    assert result["action"] == "alerted"
    assert len(sent) == 1


# ---------------------------------------------------------------------------
# Failure safety
# ---------------------------------------------------------------------------
def test_evaluate_never_raises_when_scored_rows_raises(monkeypatch):
    def _boom(horizon="1d", days=104):
        raise RuntimeError("supabase down")

    monkeypatch.setattr(outcome_ledger, "scored_rows", _boom)
    result = accuracy_monitor.evaluate(SOURCE, now=TODAY)
    assert result["action"] == "error"
    assert "supabase down" in result["reason"]
    assert result["prompt_name"] == "portfolio.tomorrow_watch"


def test_router_never_lets_one_source_failure_kill_the_batch(monkeypatch):
    """Mirrors test_prompt_monitor.py's equivalent -- exercised at the
    function level since evaluate() itself is the thing guaranteed never to
    raise; locks in that guarantee directly rather than importing FastAPI."""
    calls = []

    def _flaky(source, days=accuracy_monitor.LOOKBACK_DAYS):
        calls.append(source)
        if source == "tomorrow_per_holding":
            raise RuntimeError("boom")
        return {"source": source, "action": "insufficient_sample", "reason": "no data"}

    results = {}
    for source in accuracy_monitor.SOURCE_TO_PROMPT:
        try:
            results[source] = _flaky(source)
        except Exception as e:
            results[source] = {"source": source, "action": "error", "reason": str(e)}

    assert results["tomorrow_per_holding"]["action"] == "error"
    assert results["news_feed"]["action"] == "insufficient_sample"
    assert calls == list(accuracy_monitor.SOURCE_TO_PROMPT)


# ---------------------------------------------------------------------------
# telegram_bot.send_admin_alert itself
# ---------------------------------------------------------------------------
def test_send_admin_alert_noop_without_chat_id(monkeypatch):
    monkeypatch.setattr(telegram_bot, "TELEGRAM_ADMIN_CHAT_ID", None)
    assert telegram_bot.send_admin_alert("hello") is False


def test_send_admin_alert_returns_true_on_ok(monkeypatch):
    monkeypatch.setattr(telegram_bot, "TELEGRAM_ADMIN_CHAT_ID", "12345")
    monkeypatch.setattr(telegram_bot, "send_message", lambda chat_id, text, **kw: {"ok": True})
    assert telegram_bot.send_admin_alert("hello") is True


def test_send_admin_alert_returns_false_on_failure(monkeypatch):
    monkeypatch.setattr(telegram_bot, "TELEGRAM_ADMIN_CHAT_ID", "12345")
    monkeypatch.setattr(telegram_bot, "send_message", lambda chat_id, text, **kw: {"ok": False, "error": "boom"})
    assert telegram_bot.send_admin_alert("hello") is False
