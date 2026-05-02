"""
Compliance / disclaimer module
==============================
FinContext operates without SEBI Research Analyst registration. Every analytical
output that surfaces a recommendation, score, signal, or projected number must
carry a disclaimer that reframes it as educational/informational rather than
actionable advice.

This module is the SINGLE source of disclaimer text. All routers and any
future services that emit analytical output must pull from here — never inline
the string elsewhere, otherwise the wording will drift.

Usage:
    from app.core.compliance import with_disclaimer

    return with_disclaimer({"verdict": ..., "score": ...})

The helper attaches a `disclaimer` key. Frontends are expected to render it
beneath any recommendation surface.
"""

DISCLAIMER_TEXT = (
    "Educational and informational only. Not investment advice and not a "
    "recommendation to buy, sell, or hold any security. Numbers, signals, "
    "and labels shown here are derived from publicly available data and AI "
    "synthesis, may be incomplete or outdated, and should not be the sole "
    "basis for any investment decision. Do your own research and consult a "
    "SEBI-registered investment adviser before acting."
)

# Short tag suitable for inline UI placement (e.g. footer chip).
DISCLAIMER_SHORT = "Educational only — not investment advice."


def with_disclaimer(payload: dict) -> dict:
    """Attach the standard disclaimer to a response payload.

    Idempotent — calling twice does not duplicate the field. Returns the same
    dict (mutated) so it can be used inline in `return with_disclaimer(...)`.
    """
    if not isinstance(payload, dict):
        return payload
    payload.setdefault("disclaimer", DISCLAIMER_TEXT)
    payload.setdefault("disclaimer_short", DISCLAIMER_SHORT)
    return payload


def disclaimer_event() -> dict:
    """SSE-friendly disclaimer event — for streaming endpoints to emit before [DONE]."""
    return {"type": "disclaimer", "text": DISCLAIMER_TEXT, "short": DISCLAIMER_SHORT}
