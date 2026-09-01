"""
Shared AI client.

Provider-agnostic interface used across routers (generate_text, generate_json,
generate_grounded_json, verify_claims).

Provider precedence:
  1. OpenAI  — when OPENAI_API_KEY is set (recommended for production quality)
  2. Groq    — when GROQ_API_KEY is set (fallback / cheap inference)

Set OPENAI_MODEL or GROQ_MODEL in env to control which model is used. Both SDKs
expose the same chat.completions.create() shape, so the call sites are identical.
"""

import json
import logging
import os
import time

from dotenv import load_dotenv

from app.services.llm import llm_trace

logger = logging.getLogger(__name__)
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

_client = None
_provider: str | None = None
MODEL: str = ""

# Prefer OpenAI when the key is set.
if OPENAI_API_KEY:
    try:
        from openai import OpenAI
        _client = OpenAI(api_key=OPENAI_API_KEY)
        _provider = "openai"
        MODEL = OPENAI_MODEL
        logger.info(f"OpenAI client enabled (model={MODEL}).")
    except Exception as e:
        logger.error(f"Failed to initialize OpenAI client: {e}")
        _client = None

if _client is None and GROQ_API_KEY:
    try:
        from groq import Groq
        _client = Groq(api_key=GROQ_API_KEY)
        _provider = "groq"
        MODEL = GROQ_MODEL
        logger.info(f"Groq client enabled (model={MODEL}).")
    except Exception as e:
        logger.error(f"Failed to initialize Groq client: {e}")
        _client = None

if _client is None:
    logger.warning("No AI key set (OPENAI_API_KEY / GROQ_API_KEY) — AI features disabled.")


# Standing instruction injected into every grounded call. Keeps the model from
# inventing numbers: unsupported fields must be null and listed under data_gaps.
GROUNDING_CONTRACT = """You are an analyst that answers STRICTLY from the CONTEXT block below.

Hard rules:
1. Use ONLY facts present in CONTEXT. Do NOT use outside knowledge for numeric claims.
2. If a requested field cannot be supported by CONTEXT, set its value to null and add an entry to `data_gaps` explaining what was missing.
3. Every element of any `rationale`, `pros`, `cons`, or similar list MUST be an object with keys `text` and `source`, where `source` names the CONTEXT path that backs the claim (e.g. "ratios.profitability.roe", "news[2]", "peers.median_pe"). No bare strings.
4. Include a top-level `confidence` field: "low" | "medium" | "high" — "high" only if every numeric field is directly present in CONTEXT.
5. Respond with a single JSON object. No markdown, no commentary.
"""


def is_available() -> bool:
    return _client is not None


def provider() -> str | None:
    """Returns 'openai' | 'groq' | None — useful for logs and the /_debug endpoint."""
    return _provider


def _missing_key_error() -> RuntimeError:
    return RuntimeError("No AI provider configured (set OPENAI_API_KEY or GROQ_API_KEY).")


def generate_text(
    prompt: str,
    max_tokens: int = 2048,
    system: str | None = None,
    temperature: float = 0.7,
) -> str:
    """Synchronous text generation."""
    if not _client:
        raise _missing_key_error()

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    with llm_trace.span("ai_client.generate_text", provider=_provider, model=MODEL) as t:
        resp = _client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        usage = getattr(resp, "usage", None)
        if usage is not None:
            t.record(tokens_in=getattr(usage, "prompt_tokens", None),
                      tokens_out=getattr(usage, "completion_tokens", None))
        return resp.choices[0].message.content or ""


def generate_json(
    prompt: str,
    max_tokens: int = 2048,
    system: str | None = None,
    temperature: float = 0.2,
) -> str:
    """Native JSON mode — guaranteed valid JSON string. Works on OpenAI + Groq."""
    if not _client:
        raise _missing_key_error()

    sys_msg = (system + "\n\n" if system else "") + "Respond with a single valid JSON object. No markdown, no commentary."
    messages = [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": prompt},
    ]

    with llm_trace.span("ai_client.generate_json", provider=_provider, model=MODEL) as t:
        resp = _client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            temperature=temperature,
        )
        usage = getattr(resp, "usage", None)
        if usage is not None:
            t.record(tokens_in=getattr(usage, "prompt_tokens", None),
                      tokens_out=getattr(usage, "completion_tokens", None))
        return resp.choices[0].message.content or "{}"


def generate_grounded_json(
    task: str,
    context: dict,
    schema_description: str,
    max_tokens: int = 2048,
    temperature: float = 0.2,
    prompt_meta: dict | None = None,
    metrics_out: dict | None = None,
    prompt_client: object | None = None,
) -> dict:
    """
    Run an analytical JSON task that MUST cite fields from the provided context.

    `prompt_meta` (optional): {"name", "version", "source"} from
    prompt_registry.get_prompt() — the caller's current Langfuse-managed
    prompt, if this call site is wired to one (see prompt_registry.py /
    AGENTS.md path-back leg 3b). When given, it's stamped onto the trace
    span (`prompt_name`/`prompt_version`/`prompt_source`) so a trace is
    attributable to the exact prompt version that produced it — the trace-
    side half of the same audit trail portfolio_intelligence.py already
    writes into ai_predictions.metadata.prompt for stored predictions.
    Omitted (None) for every call site not yet wired to a versioned prompt —
    behavior is byte-identical to before this parameter existed.

    `prompt_client` (optional): the live Langfuse prompt object from
    prompt_registry.PromptResult.client. Passing it links this generation to
    that prompt version natively in Langfuse, which is what populates the
    per-version metrics view (latency/cost/scores grouped by version) — a
    strictly better join than the string stamps in `prompt_meta`, which stay
    for the local log line, for Supabase, and for call sites with no
    Langfuse-managed prompt. Kept separate from `prompt_meta` on purpose:
    that dict gets persisted to ai_predictions.metadata, and a live SDK
    object must never end up in a database row.

    `metrics_out` (optional): a caller-owned dict this function fills in
    place (never replaces) with this call's deterministic metrics —
    confidence, data_gaps_count, parse_error, tokens_in, tokens_out,
    duration_ms — before returning, on BOTH the success path and the
    parse-failure path (the parse-failure case matters most: it's the only
    signal prompt_monitor.py's schema_validation_failure_rate has, since a
    failed call produces no ai_predictions rows at all — see
    outcome_ledger.log_call_metrics' docstring). The caller decides what to
    do with it (portfolio_intelligence.py passes it to
    outcome_ledger.log_call_metrics); this function has no opinion on
    persistence. Left untouched (None) by every call site not opted in —
    zero behavior change otherwise.

    Returns the parsed JSON dict. On parse failure returns {} (caller handles fallback).
    """
    if not _client:
        raise _missing_key_error()

    # Compact separators, not indent=2. The CONTEXT block is the largest part of
    # every grounded prompt (the news-feed annotation ships ~40 candidates plus
    # per-ticker technicals), and pretty-printing it spends ~15-20% of those
    # tokens on whitespace that carries no signal — the model reads the same
    # structure either way. Cuts prefill latency and per-call cost on every
    # grounded surface. If a grounding eval regresses after this, this line is
    # the first thing to revert.
    context_json = json.dumps(context, separators=(",", ":"), default=str)
    user_prompt = (
        f"TASK:\n{task}\n\n"
        f"REQUIRED SCHEMA:\n{schema_description}\n\n"
        f"CONTEXT (your only source of truth):\n```json\n{context_json}\n```\n"
    )

    messages = [
        {"role": "system", "content": GROUNDING_CONTRACT},
        {"role": "user", "content": user_prompt},
    ]
    span_meta = dict(provider=_provider, model=MODEL, context_chars=len(context_json))
    prompt_obj = None
    if prompt_meta:
        # Prefixed so these sit next to the other stamped fields in the trace
        # JSON/Langfuse observation without colliding with `model` above (a
        # prompt_meta dict never carries that key, but be explicit anyway).
        span_meta["prompt_name"] = prompt_meta.get("name")
        span_meta["prompt_version"] = prompt_meta.get("version")
        span_meta["prompt_source"] = prompt_meta.get("source")
    # Native prompt→generation link. Deliberately its own parameter rather
    # than a key inside `prompt_meta`: callers reuse that same dict as the
    # ai_predictions.metadata.prompt audit trail written to Supabase, and a
    # live SDK object has no business being serialized into a database row.
    prompt_obj = prompt_client
    with llm_trace.span("ai_client.generate_grounded_json", prompt=prompt_obj, **span_meta) as t:
        t.record_content(input=user_prompt)
        resp = _client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            temperature=temperature,
        )
        usage = getattr(resp, "usage", None)
        if usage is not None:
            t.record(tokens_in=getattr(usage, "prompt_tokens", None),
                      tokens_out=getattr(usage, "completion_tokens", None))
        raw = resp.choices[0].message.content or "{}"
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.error("generate_grounded_json: invalid JSON. first 500 chars=%s", raw[:500])
            t.record(parse_error=True)
            t.record_content(output=raw)
            score_map = _score_grounded_call(t, {}, context)
            if metrics_out is not None:
                metrics_out.update(
                    confidence=None, data_gaps_count=None, parse_error=True,
                    tokens_in=t.extra.get("tokens_in"), tokens_out=t.extra.get("tokens_out"),
                    duration_ms=round((time.monotonic() - t.started_at) * 1000, 1),
                    trace_id=t.trace_id,
                    observation_id=t.observation_id,
                    task_text=task,
                    schema_description=schema_description,
                    output_snapshot=raw,
                    grounding_scores=score_map,
                )
            return {}
        confidence = parsed.get("confidence") if isinstance(parsed, dict) else None
        data_gaps_count = len(parsed.get("data_gaps") or []) if isinstance(parsed, dict) else None
        t.record(confidence=confidence, data_gaps=data_gaps_count)
        t.record_content(output=parsed)
        score_map = _score_grounded_call(t, parsed, context)
        if metrics_out is not None:
            metrics_out.update(
                confidence=confidence, data_gaps_count=data_gaps_count, parse_error=False,
                tokens_in=t.extra.get("tokens_in"), tokens_out=t.extra.get("tokens_out"),
                duration_ms=round((time.monotonic() - t.started_at) * 1000, 1),
                # The join key for delayed scoring: whoever persists a
                # prediction from this call stores this so the market's
                # verdict can be attached to this trace days later.
                trace_id=t.trace_id,
                observation_id=t.observation_id,
                task_text=task,
                schema_description=schema_description,
                output_snapshot=parsed,
                grounding_scores=score_map,
            )
        return parsed


def _score_grounded_call(t, parsed: dict, context: dict) -> dict:
    """Attach the deterministic grounding scores to this call's trace.

    Runs on both the success and the parse-failure path — the failure case
    is the one that would otherwise be invisible, since a call that returns
    {} writes no prediction rows anywhere and would show up in Langfuse as
    merely *fewer* traces rather than worse ones.

    Import is local and the whole thing is best-effort: scoring is an
    observability nicety and must never break a user-facing generation.
    Same stance the tracer itself takes.
    """
    try:
        from app.services.observability import langfuse_scores

        scores = langfuse_scores.grounding_scores(parsed, context)
        for s in scores.values():
            t.score(s.name, s.value, data_type=s.data_type, comment=s.comment)
        return {
            s.name: {"value": s.value, "data_type": s.data_type, "comment": s.comment}
            for s in scores.values()
        }
    except Exception:
        logger.exception("grounded call scoring failed")
        return {}


def verify_claims(output: dict, context: dict, max_tokens: int = 1024) -> dict:
    """
    Second-pass verifier. Hands the output + context back to the model and asks
    it to flag/remove unsupported claims.
    """
    if not _client:
        return {"verified": output, "removed": []}

    system = (
        "You are a strict fact-checker. You receive a CLAIM object and a CONTEXT object. "
        "Your job: for every item inside any rationale/pros/cons list in CLAIM, decide if the "
        "`text` is directly supported by the path named in `source` within CONTEXT. "
        "Return JSON: {\"verified\": <CLAIM with unsupported list items removed>, "
        "\"removed\": [{\"text\":..., \"reason\":...}, ...]}. "
        "Do not alter numeric fields; only prune unsupported list items. Preserve structure."
    )
    user = (
        f"CLAIM:\n```json\n{json.dumps(output, default=str)}\n```\n\n"
        f"CONTEXT:\n```json\n{json.dumps(context, default=str)}\n```"
    )
    with llm_trace.span("ai_client.verify_claims", provider=_provider, model=MODEL) as t:
        try:
            resp = _client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            parsed = json.loads(resp.choices[0].message.content or "{}")
            if "verified" not in parsed:
                t.record(fallback=True)
                return {"verified": output, "removed": []}
            t.record(removed_count=len(parsed.get("removed") or []))
            return parsed
        except Exception as e:
            logger.warning("verify_claims failed, returning unverified output: %s", e)
            t.record(error_swallowed=str(e))
            return {"verified": output, "removed": []}
