from __future__ import annotations

from app.services.outcomes import outcome_ledger
from app.services.pathback import grounding_fixtures


def _row(**overrides):
    base = {
        "id": "fixture-1",
        "call_id": "call-1",
        "prompt_name": "portfolio.movers_attribution",
        "violation_type": "grounding.citation_validity",
        "score_value": 0.0,
        "violation_detail": "unresolvable: TESTCO_news[0]",
        "task_text": "Explain the mover.",
        "schema_description": '{"movers": [{"attribution": [{"text": str, "source": str}]}]}',
        "context_snapshot": {"holdings": [{"news": [{"headline": "order win"}]}]},
        "output_snapshot": {"movers": [{"attribution": [{"text": "order win", "source": "TESTCO_news[0]"}]}]},
    }
    base.update(overrides)
    return base


def test_fixture_case_replays_exact_rule_and_rejects_metric_disappearance(monkeypatch):
    monkeypatch.setattr(outcome_ledger, "grounding_fixture_rows", lambda name, limit=50: [_row()])
    case = grounding_fixtures.load_grounding_fixture_cases("portfolio.movers_attribution")[0]

    assert case.context == _row()["context_snapshot"]
    assert (
        case.check({"movers": [{"attribution": [{"text": "order win", "source": "holdings[0].news[0]"}]}]})
        is True
    )
    assert case.check({"movers": []}) is False


def test_drafting_evidence_contains_exact_context_output_and_rule(monkeypatch):
    monkeypatch.setattr(outcome_ledger, "grounding_fixture_rows", lambda name, limit=8: [_row()])
    evidence = grounding_fixtures.build_drafting_evidence("portfolio.movers_attribution")
    assert "grounding.citation_validity" in evidence
    assert "TESTCO_news[0]" in evidence
    assert '"holdings"' in evidence
    assert "Explain the mover." in evidence


def test_unusable_fixture_rows_are_skipped(monkeypatch):
    monkeypatch.setattr(
        outcome_ledger,
        "grounding_fixture_rows",
        lambda name, limit=50: [_row(schema_description=None), _row(violation_type="grounding.data_gaps")],
    )
    assert grounding_fixtures.load_grounding_fixture_cases("portfolio.movers_attribution") == []


def test_call_logging_creates_lightweight_fixture_without_copying_context(monkeypatch):
    calls = []

    class _Query:
        def __init__(self, table):
            self.table = table

        def insert(self, payload):
            calls.append((self.table, "insert", payload))
            return self

        def upsert(self, payload, **kwargs):
            calls.append((self.table, "upsert", payload))
            return self

        def execute(self):
            return self

    class _Client:
        def table(self, name):
            return _Query(name)

    monkeypatch.setattr(outcome_ledger, "_client", _Client())
    context = {"holdings": [{"ticker": "PRIVATE"}]}
    ok = outcome_ledger.log_call_metrics(
        "portfolio.movers_attribution",
        1,
        "langfuse",
        call_id="00000000-0000-0000-0000-000000000001",
        context_snapshot=context,
        output_snapshot={"movers": []},
        task_text="task",
        schema_description="schema",
        grounding_scores={
            "grounding.citation_validity": {"value": 0.0, "comment": "bad path"},
            "grounding.schema_valid": {"value": True, "comment": None},
            "grounding.data_gaps": {"value": 2.0, "comment": "honest gaps"},
        },
    )
    assert ok is True
    call_row = next(payload for table, op, payload in calls if table == "prompt_call_log")
    fixture_rows = next(payload for table, op, payload in calls if table == "grounding_fixtures")
    assert call_row["context_snapshot"] == context
    assert [row["violation_type"] for row in fixture_rows] == ["grounding.citation_validity"]
    assert all("context_snapshot" not in row and "output_snapshot" not in row for row in fixture_rows)
