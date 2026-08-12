#!/usr/bin/env python3
"""
scripts/prompt_gate.py — Phase 2: offline prompt-version comparison gate.

Fetches two labeled Langfuse versions of one of the two judged prompts
(portfolio.tomorrow_watch / portfolio.news_feed_annotation) and runs
app.services.prompt_gate.compare() against the fixed eval case set in
tests/evals/prompt_gate_cases.py, printing a human-readable report.

NEVER PROMOTES anything — see prompt_gate.py's module docstring. Read the
report, then (if you want to promote) do that by hand in the Langfuse UI.

Usage:
    # Compare the live production version against a pending candidate:
    python scripts/prompt_gate.py --prompt portfolio.tomorrow_watch

    # Self-comparison / noise-floor check (same label both sides):
    python scripts/prompt_gate.py --prompt portfolio.tomorrow_watch \\
        --baseline-label production --candidate-label production

    # Final check including holdout cases, more reps for a finer signal:
    python scripts/prompt_gate.py --prompt portfolio.tomorrow_watch \\
        --candidate-label candidate --holdout --n 10

Falls back to this repo's own hardcoded fallback prompt text for BOTH sides
if Langfuse isn't configured or a label doesn't resolve to a real version —
same cold-start-safe behavior as prompt_registry.get_prompt(), so this
script (and the self-comparison / noise-floor check in particular) is
runnable with zero Langfuse setup. Requires OPENAI_API_KEY or GROQ_API_KEY
either way — the eval cases make real LLM calls.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.services import langfuse_client, prompt_gate  # noqa: E402
from app.routers.portfolio_intelligence import (  # noqa: E402
    NEWS_FEED_ANNOTATION_FALLBACK_PROMPT,
    TOMORROW_WATCH_FALLBACK_PROMPT,
)
from tests.evals.prompt_gate_cases import (  # noqa: E402
    NEWS_FEED_ANNOTATION_CASES,
    TOMORROW_WATCH_CASES,
)

FALLBACKS = {
    "portfolio.tomorrow_watch": TOMORROW_WATCH_FALLBACK_PROMPT,
    "portfolio.news_feed_annotation": NEWS_FEED_ANNOTATION_FALLBACK_PROMPT,
}
CASES = {
    "portfolio.tomorrow_watch": TOMORROW_WATCH_CASES,
    "portfolio.news_feed_annotation": NEWS_FEED_ANNOTATION_CASES,
}


def _fetch_labeled_text(name: str, label: str, fallback: str) -> str:
    """Best-effort fetch of a specific label's prompt text. Never raises —
    degrades to `fallback` on any failure, same posture as
    prompt_registry.get_prompt() (this script deliberately doesn't import
    that function directly since it needs to read labels other than
    `production`, e.g. `candidate` — a read-only CLI tool is exactly the
    exception prompt_registry.py's docstring calls out: code on the request
    path never reads `candidate`, but a human-run offline report is not the
    request path)."""
    client = langfuse_client.get_client()
    if client is None:
        return fallback
    try:
        p = client.get_prompt(name, label=label, type="text", fallback=fallback)
        return p.prompt
    except Exception:
        return fallback


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prompt", required=True, choices=sorted(FALLBACKS))
    ap.add_argument("--baseline-label", default="production")
    ap.add_argument("--candidate-label", default="candidate")
    ap.add_argument("--n", type=int, default=prompt_gate.DEFAULT_N)
    ap.add_argument("--holdout", action="store_true", help="include holdout cases in this run")
    args = ap.parse_args()

    fallback = FALLBACKS[args.prompt]
    baseline_text = _fetch_labeled_text(args.prompt, args.baseline_label, fallback)
    candidate_text = _fetch_labeled_text(args.prompt, args.candidate_label, fallback)

    same_text = baseline_text == candidate_text
    print(f"prompt: {args.prompt}")
    print(f"baseline label: {args.baseline_label}   candidate label: {args.candidate_label}"
          + ("   (identical text — noise-floor check)" if same_text else ""))
    print()

    report = prompt_gate.compare(
        CASES[args.prompt], baseline_text, candidate_text,
        n=args.n, include_holdout=args.holdout,
    )
    print(prompt_gate.render_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
