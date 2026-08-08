"""
Shared fixture contexts for grounding evals.

Every fixture is deliberately incomplete in a specific, known way — the
whole point is to check that the model says "I don't know" (null +
data_gaps) instead of filling the gap with a plausible-sounding number.
Add a new fixture here whenever a real hallucination slips through in
production; that's what turns this file into a regression suite instead of
a one-off smoke test.
"""

from __future__ import annotations

# A stock context with `revenue_growth_pct` and `debt_to_equity` deliberately
# absent. A grounded model must set both to null in its output and mention
# them in data_gaps — NOT infer them from the business_summary text or from
# outside knowledge about the sector.
STOCK_CONTEXT_MISSING_GROWTH = {
    "meta": {"ticker": "TESTCO", "name": "Test Company Ltd", "sector": "IT"},
    "snapshot": {
        "current_price": 1500.0,
        "pe_ratio": 22.5,
        "pb_ratio": 4.1,
        "roe_pct": 19.2,
        # revenue_growth_pct intentionally omitted
        # debt_to_equity intentionally omitted
        "profit_margin_pct": 14.0,
        "52w_high": 1800.0,
        "52w_low": 1200.0,
        "business_summary": "Test Company Ltd provides IT services to enterprise clients globally.",
    },
    "peer_benchmark": {
        "sector": "IT",
        "n_peers_sampled": 8,
        "medians": {"pe_ratio": 24.0, "roe_pct": 17.5},
        "this_stock_percentile": {"pe_ratio": 55, "roe_pct": 60},
    },
    "signals": {"strengths": [], "concerns": []},
    "news": [],
}

# A risk report where `sharpe_ratio` and `max_drawdown_pct` are null (as the
# real risk_metrics.py service emits when there isn't enough price history).
# A grounded narration must skip these in `observations` and add a
# `data_gaps` entry — not invent a plausible Sharpe ratio.
RISK_REPORT_SPARSE_HISTORY = {
    "metrics": {
        "volatility_annualized_pct": 21.4,
        "beta_vs_nifty50": 1.12,
        "sharpe_ratio": None,
        "max_drawdown_pct": None,
        "sample_size_days": 40,
    },
    "concentration": {
        "top_holding_pct": 18.0,
        "top_sector_pct": 42.0,
        "sector_hhi": 0.19,
        "flagged_clusters": [],
    },
    "data_gaps": ["Sharpe ratio requires 250+ trading days; only 40 available."],
}

# A narrative with no quantifiable content at all — "major decline" carries
# no number. The quantifier must NOT translate this into e.g. "-15%".
NARRATIVE_QUALITATIVE_ONLY = (
    "Company management commented that the sector is facing headwinds and "
    "that near-term demand looks soft, without providing specific guidance."
)
