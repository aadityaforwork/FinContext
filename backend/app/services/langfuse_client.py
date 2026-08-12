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
    """Lazy, cached Langfuse client, or None if not configured/unavailable."""
    global _checked, _client
    if _checked:
        return _client
    _checked = True
    if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
        return None
    try:
        from langfuse import get_client as _lf_get_client
        _client = _lf_get_client()
        logger.info("Langfuse client initialized.")
    except Exception:
        logger.exception("Langfuse client init failed — Langfuse integrations disabled")
        _client = None
    return _client
