"""
Prompt registry — Langfuse-managed prompts (path-back, leg 3b)
=================================================================
Leg 1 of the path-back loop (track_record.py) closes the loop on
*conviction*: a judged track record discounts/boosts how much the ensemble
trusts a segment, but the prompt that produced the underlying call never
changes. Leg 3b is the next rung: let the prompt itself be revised without a
deploy, and (once there's real accuracy volume — see the Notion "Self-
Iterating System" doc, 3c) let a human or eval run flag underperforming
segments and relabel a candidate prompt into production.

Scope, deliberately narrow to start: only the two prompts that actually
produce *judged* predictions — portfolio_intelligence.py's tomorrow-watch
task and news-feed annotation task, the same two sources track_record.py
already calibrates. NOT the CrewAI crew backstories (narrative/risk-brief) —
those crews aren't wired to outcome_ledger, so there's no accuracy signal to
ever justify relabeling them against. Extend this to a new prompt only once
that prompt's output is actually logged + judged; versioning a prompt with
no feedback signal is process theater, not a closed loop.

Mechanism:
  - Each prompt lives in Langfuse under a name (e.g. "portfolio.tomorrow_
    watch") with a `production` label on whichever version is live. A human
    (or a future eval run, see 3c) edits the prompt in the Langfuse UI or via
    create_text_prompt, which creates a new version — labeled `candidate` by
    default, NOT auto-promoted. Promotion to production = relabeling that
    version via update_prompt_labels. Rollback = relabel the previous
    version back to `production`. No code deploy either way.
  - get_prompt() always asks for the `production` label — code never reads
    `candidate` directly. A `candidate` version only becomes live once a
    human promotes it, which is the intended review gate (see the trap-state
    lesson from leg 1: don't let anything skip the human/eval checkpoint on
    its own).
  - Cold-start / Langfuse-unset safe: with no LANGFUSE_PUBLIC_KEY configured,
    get_prompt() returns the caller-supplied fallback text immediately, no
    network call attempted — byte-identical to pre-leg-3b behavior. The
    fallback text passed in by every call site IS the current hardcoded
    prompt, so the very first deploy of this module changes nothing until
    someone actually edits a prompt in Langfuse.
  - Never raises. The Langfuse SDK's own `fallback=` kwarg to get_prompt()
    handles fetch failures when a cached-but-expired copy also isn't
    available; this module's own try/except is the outer safety net for
    everything else (client not configured, SDK raising outside that path —
    e.g. `self._resources is None` errors, which the SDK raises unconditionally
    before its own fallback logic runs).
  - `PromptResult.version`/`source` are the audit-trail fields — callers that
    log a judged prediction (portfolio_intelligence.py's _log_tomorrow_
    predictions / _log_news_feed_predictions) persist these into
    ai_predictions.metadata alongside track_record's calibration snapshot,
    same rationale as leg 1's design-review fix #3: a prediction's text
    depends on which prompt version produced it, so that version needs to be
    reconstructable after the fact, not just "whatever was live at the time"
    (which becomes unknowable once someone relabels).

Public API:
    get_prompt(name, fallback_text, label="production") -> PromptResult
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.services import langfuse_client

logger = logging.getLogger(__name__)

# Passed as the Langfuse SDK's own client-side cache TTL for get_prompt().
# Matches track_record.py's 30-min choice for the same reason: the thing
# being cached (a human's prompt edit) doesn't change faster than that, so
# this is purely about not round-tripping to Langfuse on every request.
PROMPT_CACHE_TTL_SECONDS = 1800


@dataclass(frozen=True)
class PromptResult:
    text: str
    version: int | None
    # "langfuse" (real fetch) | "fallback_no_client" (Langfuse not configured,
    # no network attempted) | "fallback_sdk" (Langfuse configured but the
    # fetch failed — SDK-level fallback kicked in) | "fallback_error" (this
    # module's own try/except caught something the SDK didn't handle).
    source: str


def get_prompt(name: str, fallback_text: str, *, label: str = "production") -> PromptResult:
    """Fetch a named prompt's `production`-labeled text, falling back to
    `fallback_text` (the caller's current hardcoded prompt) on any failure
    or if Langfuse isn't configured. Never raises.
    """
    client = langfuse_client.get_client()
    if client is None:
        return PromptResult(text=fallback_text, version=None, source="fallback_no_client")

    try:
        p = client.get_prompt(
            name,
            label=label,
            type="text",
            cache_ttl_seconds=PROMPT_CACHE_TTL_SECONDS,
            fallback=fallback_text,
        )
    except Exception:
        logger.exception("prompt_registry: get_prompt(%r) raised, using local fallback", name)
        return PromptResult(text=fallback_text, version=None, source="fallback_error")

    if getattr(p, "is_fallback", False):
        # The SDK itself couldn't fetch (network/not-found/etc.) and returned
        # the fallback we gave it instead of raising, per its own contract.
        return PromptResult(text=p.prompt, version=None, source="fallback_sdk")

    return PromptResult(text=p.prompt, version=p.version, source="langfuse")
