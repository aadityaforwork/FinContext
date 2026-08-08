"""
LLM call tracing
================
Lightweight, dependency-free observability for every LLM/agent call in the
app. Not a replacement for a real tracing product (Helicone, LangSmith,
etc.) — it's the minimum viable version: one structured log line per call,
plus an in-process ring buffer so the most recent calls are inspectable
without a log aggregator.

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
    the emitted record, it never swallows or alters control flow.
  - In-process only (like _inproc in llm_cache.py) — resets on restart, not
    shared across uvicorn workers. Good enough for local debugging. Wire
    `recent()` to a real store (a Postgres table, Helicone, etc.) before you
    need cross-worker or cross-restart history.
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

logger = logging.getLogger("llm_trace")

_RECENT_MAXLEN = 200
_recent: deque[dict] = deque(maxlen=_RECENT_MAXLEN)


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


def recent(limit: int = 50) -> list[dict]:
    """Most recent traced calls, newest first. Cheap debugging aid — wire a
    gated `/_debug/llm-traces` endpoint to this if you want it over HTTP
    (follow the ADMIN_TOKEN pattern used by /cache-stats)."""
    items = list(_recent)[-limit:]
    return list(reversed(items))
