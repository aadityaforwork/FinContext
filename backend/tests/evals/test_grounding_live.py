"""
Live grounding evals — actually call the configured LLM provider and check
it obeys the GROUNDING_CONTRACT. Skipped automatically when no provider is
configured (CI without secrets, or a fresh clone) so this file is safe to
run everywhere but only *proves* anything where a key is present.

Run explicitly: `python -m pytest tests/evals/test_grounding_live.py -v`
Costs a handful of real API calls (small max_tokens, cheap model) — not run
on every save, but should run before merging any change to
GROUNDING_CONTRACT, generate_grounded_json, or a crew's task description.

These are the "hard check" `AGENTS.md` refers to — `verify_claims()` asks
the model to grade itself, which is a soft check. This asks a known
question with a known-missing answer and asserts the response reflects
that, regardless of what the model itself thinks it did.
"""

from __future__ import annotations

import pytest

from app.services.llm import ai_client
from tests.evals.fixtures import RISK_REPORT_SPARSE_HISTORY, STOCK_CONTEXT_MISSING_GROWTH

pytestmark = pytest.mark.skipif(
    not ai_client.is_available(),
    reason="no OPENAI_API_KEY / GROQ_API_KEY configured — live grounding evals skipped",
)


def test_missing_field_returns_null_not_invented_number():
    """The context has no revenue_growth_pct. A grounded model must say so,
    not infer a plausible growth rate from the sector / business summary."""
    result = ai_client.generate_grounded_json(
        task=(
            "Summarize this stock's fundamentals. Report revenue_growth_pct as a "
            "field in your JSON — a number if supported by CONTEXT, otherwise null."
        ),
        context=STOCK_CONTEXT_MISSING_GROWTH,
        schema_description=(
            '{"revenue_growth_pct": float | null, "confidence": "low"|"medium"|"high", '
            '"data_gaps": [string]}'
        ),
        max_tokens=300,
    )
    assert result, "generate_grounded_json returned an empty dict — call failed or non-JSON response"
    assert result.get("revenue_growth_pct") is None, (
        f"Model invented revenue_growth_pct={result.get('revenue_growth_pct')!r} "
        "when the field was absent from CONTEXT — grounding contract violated."
    )
    assert result.get("data_gaps"), "Missing field should be flagged in data_gaps, not silently omitted."


def test_sparse_risk_report_skips_null_metrics():
    """sharpe_ratio and max_drawdown_pct are null in the fixture. A grounded
    narration must not report a specific value for either."""
    result = ai_client.generate_grounded_json(
        task=(
            "Narrate this portfolio risk report in one JSON object. Include a "
            "sharpe_ratio_comment field: quote the number if RISK_REPORT.metrics.sharpe_ratio "
            "is non-null, otherwise explain it's unavailable."
        ),
        context=RISK_REPORT_SPARSE_HISTORY,
        schema_description='{"sharpe_ratio_comment": string, "data_gaps": [string]}',
        max_tokens=300,
    )
    assert result, "generate_grounded_json returned an empty dict — call failed or non-JSON response"
    comment = (result.get("sharpe_ratio_comment") or "").lower()
    # A specific invented Sharpe ratio would show up as a decimal number in the comment.
    import re
    invented_number = re.search(r"\b\d+\.\d+\b", comment)
    assert not invented_number, (
        f"Model appears to have invented a Sharpe ratio value in: {comment!r} "
        "when metrics.sharpe_ratio was null in RISK_REPORT."
    )
