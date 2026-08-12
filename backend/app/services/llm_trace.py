"""
LLM call tracing
================
Lightweight observability for every LLM/agent call in the app: one
structured log line per call, an in-process ring buffer so the most recent
calls are inspectable without a log aggregator, and — when configured — a
Langfuse generation observation per call (latency, tokens, model, provider,
confidence/data_gaps) so calls are queryable/graphable as real traces
instead of grep-only log lines.

Deliberately does NOT send prompt/completion body text to Langfuse. Call
sites only ever pass structured metadata (ticker, model, provider, token
counts, confidence, data_gaps) into `meta`/`record()` — never the raw
prompt or CONTEXT block, which routinely contains a user's portfolio/
financial data. Same reasoning as `send_default_pii=False` on the Sentry
init in main.py: this is a financial app, the LLM observability vendor is a
third-party US-hosted service, and there's no signed DPA/compliance review
backing a decision to ship raw prompt bodies there. If you want full
prompt/response capture for debugging model quality, that's a deliberate
follow-up decision to make explicitly (see AGENTS.md compliance posture),
not a side effect of adding tracing.

Why this exists: with 7+ AI surfaces (direct ai_client.py calls + CrewAI
crews) and no captured history of prompt/context/completion, there was no
way to answer "what did the model actually see when it produced this
output" after the fact. This gives every call site a one-line integration:

    from app.services import llm_trace

    with llm_trace.span("deep_dive.verdict", ticker=ticker) as t:
        result = ai_client.generate_grounded_json(...)
        t.record(provider=ai_client.provider(), model=ai_client.MODEL)

Design notes:
  - Never raises on its own bookkeeping. If the wrapped call raises, that
    exception propagates untouched — tracing only adds an `error` field to
    the emitted record, it never swallows or alters control flow. Same goes
    for the Langfuse side: any SDK failure is logged and swallowed.
  - In-process ring buffer (like _inproc in llm_cache.py) — resets on
    restart, not shared across workers. Langfuse is the durable, cross-
    worker/cross-restart store; `recent()` stays for cheap local debugging.
  - Langfuse is opt-in and no-op unless LANGFUSE_PUBLIC_KEY is set (same
    pattern as SENTRY_DSN in main.py) — local/CI runs with no key configured
    behave exactly as before this was added.
  - The backend runs as a Vercel serverless function (see root vercel.json
    experimentalServices), not a long-lived process — the function can be
    frozen the instant a response is sent, before the SDK's background
    batching thread gets scheduled. So each span flushes synchronously
    instead of relying on Langfuse's default background flush. That costs a
    bit of per-call latency but avoids silently losing every trace, which
    is the actual point of wiring this up. Revisit if this ever moves to a
    persistent host (Render, etc.) — background flush would be strictly
    better there.
  - The emitted log line is a single `logger.info("llm_trace %s", json)` —
    grep-able locally, and shippable to any log drain (Render logs, etc.)
    without extra plumbing.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.services import langfuse_client

logger = logging.getLogger("llm_trace")

_RECENT_MAXLEN = 200
_recent: deque[dict] = deque(maxlen=_RECENT_MAXLEN)


def _get_langfuse():
    """Lazy, cached Langfuse client — see langfuse_client.get_client() (shared
    with prompt_registry.py). Returns None (and stays None) if
    LANGFUSE_PUBLIC_KEY isn't set or the SDK/init fails — tracing is always
    additive, never a hard dependency for the AI surfaces to function."""
    return langfuse_client.get_client()


@dataclass
class _Span:
    name: str
    meta: dict[str, Any]
    started_at: float = field(default_factory=time.monotonic)
    extra: dict[str, Any] = field(default_factory=dict)

    def record(self, **kv: Any) -> None:
        """Attach fields once they're known — tokens, model, provider,
        cache_hit, confidence, etc. Call this any time before the `with`
        block exits; last write wins per key."""
        self.extra.update(kv)


@contextmanager
def span(name: str, **meta: Any) -> Iterator[_Span]:
    """Wrap a single LLM/agent call.

    `name` should be `"<flow>.<step>"`, e.g. `"deep_dive.verdict"`,
    `"narrative_crew.quantify"`, `"risk_brief.narrate"` — consistent enough
    to grep/group by flow later.

    Emits exactly one structured log line on exit (success or failure) and
    appends the same record to the in-process recent-calls buffer.
    """
    s = _Span(name=name, meta=dict(meta))
    error: str | None = None
    lf = _get_langfuse()
    lf_obs = None
    if lf is not None:
        try:
            lf_obs = lf.start_observation(name=name, as_type="generation", input=meta, metadata=meta)
        except Exception:
            logger.exception("Langfuse start_observation failed for %s", name)
            lf_obs = None
    try:
        yield s
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        raise
    finally:
        duration_ms = round((time.monotonic() - s.started_at) * 1000, 1)
        record = {
            "id": uuid.uuid4().hex[:12],
            "ts": datetime.now(UTC).isoformat(),
            "call": name,
            "duration_ms": duration_ms,
            "error": error,
            **s.meta,
            **s.extra,
        }
        try:
            logger.info("llm_trace %s", json.dumps(record, default=str))
        except Exception:
            logger.info("llm_trace %s (fields unserializable, dropped from log)", name)
        _recent.append(record)

        if lf_obs is not None:
            try:
                usage = {}
                if record.get("tokens_in") is not None:
                    usage["input"] = record["tokens_in"]
                if record.get("tokens_out") is not None:
                    usage["output"] = record["tokens_out"]
                output = {
                    k: v for k, v in s.extra.items()
                    if k not in ("tokens_in", "tokens_out", "model")
                } or None
                lf_obs.update(
                    output=output,
                    model=record.get("model"),
                    usage_details=usage or None,
                    level="ERROR" if error else "DEFAULT",
                    status_message=error,
                )
                lf_obs.end()
                lf.flush()  # see module docstring — serverless, can't rely on background flush
            except Exception:
                logger.exception("Langfuse observation update/flush failed for %s", name)


def recent(limit: int = 50) -> list[dict]:
    """Most recent traced calls, newest first. Cheap debugging aid — wire a
    gated `/_debug/llm-traces` endpoint to this if you want it over HTTP
    (follow the ADMIN_TOKEN pattern used by /cache-stats)."""
    items = list(_recent)[-limit:]
    return list(reversed(items))
