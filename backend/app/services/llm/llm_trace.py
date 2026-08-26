"""
LLM call tracing
================
Lightweight observability for every LLM/agent call in the app: one
structured log line per call, an in-process ring buffer so the most recent
calls are inspectable without a log aggregator, and — when configured — a
Langfuse generation observation per call (latency, tokens, model, provider,
confidence/data_gaps) so calls are queryable/graphable as real traces
instead of grep-only log lines.

CONTENT CAPTURE IS A DELIBERATE, REVERSIBLE DECISION — READ BEFORE CHANGING.
This module originally sent structured metadata ONLY (model, provider,
tokens, confidence, data_gaps) and never the prompt or CONTEXT body, on the
reasoning that CONTEXT routinely carries a real user's portfolio and
financial position, Langfuse is a third-party US-hosted service, and no
DPA/compliance review backed shipping that there — the same reasoning as
`send_default_pii=False` on the Sentry init in main.py.

That decision was explicitly reversed by the project owner on 2026-08-16 to
unlock Langfuse's dataset/experiment and full-trace-debugging features (see
memory/gotcha_langfuse_content_capture.md for the decision record and what
it obliges — privacy-policy wording, vendor DPA, deletion path). It is
gated behind ONE env var so it can be turned off without a deploy:

    LANGFUSE_CAPTURE_CONTENT=false   -> metadata-only, the original posture
    (unset / anything else)          -> full input+output capture

Everything else in this module is metadata regardless of that flag. If you
are adding a new AI surface that handles data more sensitive than a
portfolio snapshot (identity documents, bank credentials, anything covered
by a different consent), do not assume this flag covers it — check the
decision record first.

Why this exists: with 7+ AI surfaces (direct ai_client.py calls + CrewAI
crews) and no captured history of prompt/context/completion, there was no
way to answer "what did the model actually see when it produced this
output" after the fact. This gives every call site a one-line integration:

    from app.services.llm import llm_trace

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
import os
import time
import uuid
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.services.observability import langfuse_client

logger = logging.getLogger("llm_trace")

_RECENT_MAXLEN = 200
_recent: deque[dict] = deque(maxlen=_RECENT_MAXLEN)

# Hard cap on any single captured body. A news-feed annotation CONTEXT runs
# past 31k chars; shipping every one of those in full buys nothing for
# debugging and turns a cheap trace into an expensive one. Truncation is
# marked inline so a reader never mistakes a cut body for the real prompt.
_MAX_CAPTURE_CHARS = 12000


def _capture_enabled() -> bool:
    """Whether to send prompt/completion bodies. See the module docstring —
    this is the single switch for the 2026-08-16 content-capture decision.

    Read per call rather than cached at import: the same reasoning
    langfuse_client.get_client() documents for not caching its negative
    result — this module never calls load_dotenv() itself, so a value cached
    at import time could lock in whatever was visible before .env loaded.
    """
    return os.environ.get("LANGFUSE_CAPTURE_CONTENT", "true").strip().lower() not in (
        "false", "0", "no", "off",
    )


def _clip(value: Any) -> Any:
    """Truncate a captured body to _MAX_CAPTURE_CHARS, marking the cut."""
    try:
        if isinstance(value, str) and len(value) > _MAX_CAPTURE_CHARS:
            return value[:_MAX_CAPTURE_CHARS] + f"\n…[truncated {len(value) - _MAX_CAPTURE_CHARS} chars]"
    except Exception:
        return value
    return value


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
    # Langfuse ids, populated once the observation exists. `trace_id` is the
    # join key everything delayed depends on — outcome_ledger persists it
    # next to a prediction so the market's verdict can find its way back to
    # this exact call a day or twenty trading days later.
    trace_id: str | None = None
    observation_id: str | None = None
    _obs: Any = None
    _content: dict[str, Any] = field(default_factory=dict)

    def record(self, **kv: Any) -> None:
        """Attach fields once they're known — tokens, model, provider,
        cache_hit, confidence, etc. Call this any time before the `with`
        block exits; last write wins per key."""
        self.extra.update(kv)

    def record_content(self, *, input: Any = None, output: Any = None) -> None:
        """Attach the actual prompt/response bodies.

        Honours LANGFUSE_CAPTURE_CONTENT — when capture is off this is a
        no-op, so call sites can pass bodies unconditionally and the switch
        stays in exactly one place. Bodies never reach the local log line or
        the in-process ring buffer either way; they only ever go to Langfuse.
        """
        if not _capture_enabled():
            return
        if input is not None:
            self._content["input"] = _clip(input)
        if output is not None:
            self._content["output"] = _clip(output)

    def score(self, name: str, value: float | str | bool, *,
              data_type: str | None = None, comment: str | None = None) -> None:
        """Attach a score to this observation inline.

        Convenience for the call-time deterministic scores; anything delayed
        (the market outcome) goes through langfuse_scores.record_score with a
        stored trace_id instead, because by then this span is long gone.
        Never raises."""
        if self._obs is None:
            return
        try:
            self._obs.score(name=name, value=value, data_type=data_type, comment=comment)
        except Exception:
            logger.exception("llm_trace: inline score %r failed", name)


@contextmanager
def span(name: str, *, prompt: Any = None, **meta: Any) -> Iterator[_Span]:
    """Wrap a single LLM/agent call.

    `name` should be `"<flow>.<step>"`, e.g. `"deep_dive.verdict"`,
    `"narrative_crew.quantify"`, `"risk_brief.narrate"` — consistent enough
    to grep/group by flow later.

    `prompt` (optional): the Langfuse prompt client object from
    prompt_registry.get_prompt().client. Passing it links this generation to
    that prompt version *natively*, which is what populates Langfuse's
    per-version metrics page — strictly better than the
    `prompt_name`/`prompt_version` metadata stamps, which stay for the
    local log line and for call sites with no Langfuse-managed prompt.

    If a `flow()` is active, this observation nests under it automatically
    (OpenTelemetry context propagation) — no plumbing needed at call sites.

    Emits exactly one structured log line on exit (success or failure) and
    appends the same record to the in-process recent-calls buffer.
    """
    s = _Span(name=name, meta=dict(meta))
    error: str | None = None
    lf = _get_langfuse()
    lf_obs = None
    if lf is not None:
        try:
            lf_obs = lf.start_observation(
                name=name, as_type="generation",
                input=meta, metadata=meta, prompt=prompt,
            )
            s._obs = lf_obs
            s.trace_id = getattr(lf_obs, "trace_id", None)
            s.observation_id = getattr(lf_obs, "id", None)
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
                # When content capture is on, the real bodies replace the
                # metadata-shaped input/output. The metadata itself is still
                # on the observation (set at start, and in `metadata` here),
                # so nothing is lost by preferring the real thing.
                update_kwargs: dict[str, Any] = {}
                if s._content.get("input") is not None:
                    update_kwargs["input"] = s._content["input"]
                update_kwargs["output"] = (
                    s._content["output"] if s._content.get("output") is not None else output
                )
                lf_obs.update(
                    model=record.get("model"),
                    usage_details=usage or None,
                    metadata={k: v for k, v in record.items() if k != "id"},
                    level="ERROR" if error else "DEFAULT",
                    status_message=error,
                    **update_kwargs,
                )
                lf_obs.end()
                lf.flush()  # see module docstring — serverless, can't rely on background flush
            except Exception:
                logger.exception("Langfuse observation update/flush failed for %s", name)


@contextmanager
def flow(
    name: str,
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    tags: list[str] | None = None,
    **meta: Any,
) -> Iterator[Any]:
    """Group every LLM call made inside this block into ONE trace.

    Why this exists: without it, every `span()` starts its own root trace, so
    a single dashboard load that fires five grounded calls shows up in
    Langfuse as five unrelated traces with no parent and no way to tell they
    belonged together. That makes "this user's morning brief was slow"
    unanswerable — you can see five slow calls but not the flow they
    composed. Wrapping a router handler in `flow()` gives the calls a shared
    root, a shared session, and a shared user.

    Usage — one per user-facing operation, at the router layer:

        with llm_trace.flow("morning_brief", user_id=uid, session_id=req_id):
            ...                       # every span() inside nests under this

    `user_id`: pass an OPAQUE, STABLE id (the Supabase user uuid), never an
    email or a name. It's the join key for "show me this complaint's traces"
    and nothing more — the 2026-08-16 content-capture decision covers
    portfolio context, not contact details.

    Nesting works through OpenTelemetry context, so `span()` needs no
    argument to find its parent. Never raises, and yields None when Langfuse
    isn't configured, so the block always runs.
    """
    lf = _get_langfuse()
    if lf is None:
        yield None
        return

    try:
        from langfuse import propagate_attributes
    except Exception:
        logger.exception("llm_trace.flow: propagate_attributes import failed")
        propagate_attributes = None  # type: ignore[assignment]

    started = time.monotonic()
    # Build the scaffolding OUTSIDE the yield path. A try/except wrapped
    # around the `yield` itself would swallow the body's own exception and
    # then yield a second time — so setup failures are handled here, and
    # anything the body raises propagates untouched (same stance as span()).
    try:
        root_cm = lf.start_as_current_observation(
            name=name, as_type="span", input=meta or None, metadata=meta or None,
        )
    except Exception:
        logger.exception("llm_trace.flow(%s) scaffolding failed; running untraced", name)
        yield None
        return

    try:
        with root_cm as root:
            if propagate_attributes is not None:
                with propagate_attributes(
                    user_id=user_id, session_id=session_id,
                    tags=tags, trace_name=name,
                ):
                    yield root
            else:
                yield root
    finally:
        logger.info(
            "llm_trace_flow %s",
            json.dumps({"flow": name, "duration_ms": round((time.monotonic() - started) * 1000, 1),
                        "session_id": session_id, **meta}, default=str),
        )
        try:
            lf.flush()  # serverless — see module docstring
        except Exception:
            logger.exception("llm_trace.flow: flush failed for %s", name)


def recent(limit: int = 50) -> list[dict]:
    """Most recent traced calls, newest first. Cheap debugging aid — wire a
    gated `/_debug/llm-traces` endpoint to this if you want it over HTTP
    (follow the ADMIN_TOKEN pattern used by /cache-stats)."""
    items = list(_recent)[-limit:]
    return list(reversed(items))
