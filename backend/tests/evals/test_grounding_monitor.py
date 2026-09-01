from __future__ import annotations

from app.services.notify import telegram_bot
from app.services.outcomes import outcome_ledger
from app.services.pathback import grounding_monitor

PROMPT = "portfolio.movers_attribution"
RULE = "grounding.citation_validity"


def _rows(values):
    return [{"prompt_name": PROMPT, "grounding_scores": {RULE: {"value": value}}} for value in values]


def test_insufficient_sample_is_noop(monkeypatch):
    monkeypatch.setattr(outcome_ledger, "grounding_score_rows", lambda days=7: _rows([0, 1]))
    result = grounding_monitor.evaluate(PROMPT, RULE)
    assert result["action"] == "insufficient_sample"


def test_below_failure_threshold_is_noop(monkeypatch):
    monkeypatch.setattr(outcome_ledger, "grounding_score_rows", lambda days=7: _rows([0, 1, 1, 1, 1, 1]))
    result = grounding_monitor.evaluate(PROMPT, RULE)
    assert result["action"] == "no_action"
    assert result["failure_rate_pct"] == 16.7


def test_threshold_crossing_alerts_and_logs_independently(monkeypatch):
    monkeypatch.setattr(outcome_ledger, "grounding_score_rows", lambda days=7: _rows([0, 0, 1, 1, 1]))
    monkeypatch.setattr(outcome_ledger, "last_grounding_alert", lambda *a, **kw: None)
    sent = []
    logged = []
    monkeypatch.setattr(telegram_bot, "send_admin_alert", lambda message: sent.append(message) or True)
    monkeypatch.setattr(
        outcome_ledger, "log_grounding_alert", lambda *a, **kw: logged.append((a, kw)) or True
    )

    result = grounding_monitor.evaluate(PROMPT, RULE)
    assert result["action"] == "alerted"
    assert result["failure_rate_pct"] == 40.0
    assert "independent of market accuracy" in sent[0]
    assert logged[0][0] == (PROMPT, RULE)


def test_recent_alert_enforces_per_rule_cooldown(monkeypatch):
    monkeypatch.setattr(outcome_ledger, "grounding_score_rows", lambda days=7: _rows([0, 0, 1, 1, 1]))
    monkeypatch.setattr(outcome_ledger, "last_grounding_alert", lambda *a, **kw: {"created_at": "now"})
    monkeypatch.setattr(
        telegram_bot, "send_admin_alert", lambda message: (_ for _ in ()).throw(AssertionError())
    )
    result = grounding_monitor.evaluate(PROMPT, RULE)
    assert result["action"] == "already_alerted_recently"


def test_missing_score_is_not_in_denominator(monkeypatch):
    rows = _rows([0, 1, 1, 1, 1]) + [{"prompt_name": PROMPT, "grounding_scores": {}}]
    monkeypatch.setattr(outcome_ledger, "grounding_score_rows", lambda days=7: rows)
    monkeypatch.setattr(outcome_ledger, "last_grounding_alert", lambda *a, **kw: {"created_at": "now"})
    result = grounding_monitor.evaluate(PROMPT, RULE)
    assert result["recent_n"] == 5
    assert result["failure_rate_pct"] == 20.0
