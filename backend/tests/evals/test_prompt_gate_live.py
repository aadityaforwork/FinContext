"""
Live prompt-gate eval — actually calls the configured LLM provider N times
per case against the current `production`-labeled (or fallback) text of
portfolio.movers_attribution / portfolio.tomorrow_watch /
portfolio.news_feed_annotation and reports a
pass rate, using eval_runner.py + app/services/prompt_eval_cases.py
(re-exported here for back-compat via tests/evals/prompt_gate_cases.py).

Same skip/cost posture as test_grounding_live.py: skipped automatically with
no provider configured, real (small) API spend when one is. Run explicitly
and read the printed table:

    python -m pytest tests/evals/test_prompt_gate_live.py -v -s

This file intentionally does NOT import prompt_registry / hit Langfuse — it
runs the case set against the literal fallback prompt text (the same text
that ships as each prompt's seed version) so it works identically whether or
not LANGFUSE_PUBLIC_KEY is configured. Phase 2's comparison gate is what
actually diffs two Langfuse-fetched versions against each other.
"""

from __future__ import annotations

import pytest

from app.routers.portfolio_intelligence import (
    MOVERS_ATTRIBUTION_FALLBACK_PROMPT,
    NEWS_FEED_ANNOTATION_FALLBACK_PROMPT,
    TOMORROW_WATCH_FALLBACK_PROMPT,
)
from app.services.llm import ai_client
from app.services.pathback import eval_runner
from app.services.pathback.prompt_eval_cases import ALL_CASES

pytestmark = pytest.mark.skipif(
    not ai_client.is_available(),
    reason="no OPENAI_API_KEY / GROQ_API_KEY configured — live prompt-gate eval skipped",
)


def test_current_fixtures_pass_rate_at_n5(capsys):
    """Not a strict pass/fail gate (that's Phase 2) — Phase 1 just needs the
    eval runner wired end to end and the pass rates visible."""
    fallback_by_prompt = {
        "portfolio.movers_attribution": MOVERS_ATTRIBUTION_FALLBACK_PROMPT,
        "portfolio.tomorrow_watch": TOMORROW_WATCH_FALLBACK_PROMPT,
        "portfolio.news_feed_annotation": NEWS_FEED_ANNOTATION_FALLBACK_PROMPT,
    }

    all_results = []
    for case in ALL_CASES:
        prompt_text = fallback_by_prompt[case.prompt_name]
        result = eval_runner.run_case(case, prompt_text, n=5)
        all_results.append(result)

    summary = eval_runner.summarize(all_results)
    with capsys.disabled():
        print("\n\nPrompt-gate eval — current fixtures @ N=5\n" + "=" * 60)
        for r in all_results:
            print(f"  {r.case_id:55s} {r.passes}/{r.n}  ({r.pass_rate:.0%})  errors={r.errors}")
        print("-" * 60)
        print(f"  overall pass rate: {summary['overall_pass_rate']:.0%}  "
              f"total errors: {summary['total_errors']}")
        print("=" * 60)

    # Sanity assertions, not a promotion gate: every case should at least run
    # without erroring out on every rep (a 5/5 error count would mean the
    # fixture itself is broken, not that the prompt failed the check).
    for r in all_results:
        assert r.errors < r.n, f"{r.case_id}: every rep errored — fixture is likely broken, not the prompt"
