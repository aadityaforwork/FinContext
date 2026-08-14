"""
Back-compat re-export. The real content moved to
app/services/prompt_eval_cases.py as of path-back leg 3e (prompt_drafter.py
needs these cases at runtime, not just from a test/CLI context — see that
module's own docstring for why app code can't reach into backend/tests/).

Kept here, unchanged in shape, purely so `scripts/prompt_gate.py` and
`test_prompt_gate_live.py` didn't need an import-path change too. New code
should import from app.services.prompt_eval_cases directly.
"""

from __future__ import annotations

from app.services.prompt_eval_cases import (  # noqa: F401
    ALL_CASES,
    CASE_NEWS_POLICY_SECTOR_MAPPING,
    CASE_NEWS_TECHNICALS_CONTRADICT_MIXED,
    CASE_TOMORROW_NO_BANNED_PHRASES,
    CASE_TOMORROW_NO_CATALYST_EXCLUDED,
    NEWS_FEED_ANNOTATION_CASES,
    TOMORROW_WATCH_CASES,
)
