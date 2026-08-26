"""
Shared lazy Langfuse client accessor
=====================================
Both llm_trace.py (call tracing) and prompt_registry.py (prompt versioning —
see AGENTS.md / memory/ path-back leg 3b) need the exact same opt-in,
never-hard-fail Langfuse client. Extracted here so that lazy-init lives in
one place instead of being copy-pasted per call site — see
memory/gotcha_config_env_sprawl.md for the general sprawl pattern this
avoids adding a third instance of.

Opt-in: get_client() returns None (and stays None for the process lifetime)
unless LANGFUSE_PUBLIC_KEY is set. Never raises — any SDK import/init
failure is logged and degrades to None, so callers can treat "no client" and
"Langfuse not configured" identically without their own try/except.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_checked = False
_client = None


def get_client():
    """Lazy, cached Langfuse client, or None if not configured/unavailable.

    The "not configured" case is deliberately NOT cached. `_checked` is only
    set once we've actually attempted an init with a key present, because
    this module reads os.environ directly and never calls load_dotenv()
    itself — so whether the key is visible depends on whether something else
    has loaded .env yet. Caching a negative result here would mean a single
    call that lands before dotenv (an import-time call in a script, a test
    that imports before its fixture runs) permanently disables Langfuse for
    the whole process, silently and unrecoverably. Platform-provided env
    (Vercel/Render) is present from process start so this only bites local
    and script contexts — but it bites them invisibly, which is worse.
    """
    global _checked, _client
    if _checked:
        return _client
    if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
        return None  # not cached — see docstring
    _checked = True
    try:
        from langfuse import get_client as _lf_get_client # type: ignore
        _client = _lf_get_client()
        logger.info("Langfuse client initialized.")
    except Exception:
        logger.exception("Langfuse client init failed — Langfuse integrations disabled")
        _client = None
    return _client
