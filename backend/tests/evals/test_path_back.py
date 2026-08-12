"""
Path-back trap-state regression tests
======================================
track_record.py's calibration factor is derived from outcome_ledger history.
If the code that logs predictions ever started skipping items hidden by the
conviction gate, a segment could get unlucky, drop below the gate, stop
producing logged/scored predictions, and never accumulate the data needed to
earn its way back — a one-way door that freezes a bad (or merely unlucky)
track record forever. See the TRAP-STATE INVARIANT comment above
_log_tomorrow_predictions in portfolio_intelligence.py.

These tests lock in the fix: log everything, including hidden items; only
the response payload (built separately, elsewhere in the router) hides them
from the user. Also locks in that the calibration audit trail (factor,
tier sample sizes, hit rate) actually reaches ai_predictions.metadata.

No API key / Supabase / network required — outcome_ledger.log_predictions
is monkeypatched to capture what it was called with.
"""

from __future__ import annotations

import app.routers.portfolio_intelligence as pi


def test_log_tomorrow_predictions_logs_hidden_items_too(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        pi.outcome_ledger, "log_predictions",
        lambda rows: captured.setdefault("rows", rows),
    )

    tomorrow_data = {
        "per_holding": [
            {
                "ticker": "TCS", "direction": "positive", "catalyst_type": "earnings",
                "importance": "high", "what_to_watch": "x", "sources": [], "sector": "IT",
                "conviction": 70,
            },
            {
                # Hidden by the conviction gate — must still be logged.
                "ticker": "INFY", "direction": "negative", "catalyst_type": "technical",
                "importance": "low", "what_to_watch": "y", "sources": [], "sector": "IT",
                "conviction": 30, "hidden_low_conviction": True,
                "raw_conviction": 45, "calibration_factor": 0.7,
                "calibration_hit_rate_pct": 20.0, "calibration_pair_n": 12,
                "calibration_source_n": 12, "calibration_global_n": 12,
            },
        ]
    }
    movers_ctx = {"holdings": [
        {"ticker": "TCS", "current_price": 3500, "technicals": {}},
        {"ticker": "INFY", "current_price": 1500, "technicals": {}},
    ]}

    pi._log_tomorrow_predictions(tomorrow_data, movers_ctx)

    assert "rows" in captured, "log_predictions was never called"
    tickers_logged = {r["ticker"] for r in captured["rows"]}
    assert tickers_logged == {"TCS", "INFY"}  # the trap-state assertion

    infy_row = next(r for r in captured["rows"] if r["ticker"] == "INFY")
    cal = infy_row["metadata"]["calibration"]
    assert cal["factor"] == 0.7
    assert cal["pair_n"] == 12
    assert cal["hit_rate_pct"] == 20.0


def test_log_news_feed_predictions_logs_hidden_items_too(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        pi.outcome_ledger, "log_predictions",
        lambda rows: captured.setdefault("rows", rows),
    )

    cleaned = [
        {
            "news_id": "n1", "headline": "h1", "category": "earnings",
            "impact_level": "high", "direction": "positive",
            "affected_tickers": ["TCS"], "reason": "r1", "conviction": 70,
        },
        {
            # Hidden by the conviction gate — must still be logged.
            "news_id": "n2", "headline": "h2", "category": "sector",
            "impact_level": "low", "direction": "negative",
            "affected_tickers": ["INFY"], "reason": "r2",
            "conviction": 25, "hidden_low_conviction": True,
            "raw_conviction": 40, "calibration_factor": 0.75,
            "calibration_hit_rate_pct": 25.0, "calibration_pair_n": 15,
            "calibration_source_n": 15, "calibration_global_n": 15,
        },
    ]

    pi._log_news_feed_predictions(cleaned, {})

    assert "rows" in captured, "log_predictions was never called"
    tickers_logged = {r["ticker"] for r in captured["rows"]}
    assert tickers_logged == {"TCS", "INFY"}  # the trap-state assertion

    infy_row = next(r for r in captured["rows"] if r["ticker"] == "INFY")
    cal = infy_row["metadata"]["calibration"]
    assert cal["factor"] == 0.75
    assert cal["pair_n"] == 15
