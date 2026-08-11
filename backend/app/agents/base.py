"""
Agent base — shared LLM and grounding contract.

Single source for the LLM configuration so we don't pin Groq in 8 different
places. When the multi-provider fallback (Groq → Gemini → Anthropic) lands,
it lands here, and every agent inherits it for free.

Latency / TTFR notes (see AGENTS.md "Known gaps" before changing this file):
- get_llm() used to build the crewai.LLM client lazily on the FIRST real
  request, which put SDK import + client construction cost inside that
  user's time-to-first-response. main.py now calls prewarm() at app startup
  so that cost is paid once at boot instead. get_llm() stays lazy as a
  fallback for anything that imports this module without going through the
  FastAPI lifespan (tests, scripts).
- get_llm(fast=True) returns a second singleton pointed at a smaller/quicker
  Groq model (CREWAI_FAST_MODEL). Use it for agents doing narrow, low-risk
  extraction (see registry.make_narrative_extractor) where the accuracy
  delta vs. the default model doesn't justify the extra wall-clock time.
  Don't reach for it for anything that synthesizes a final user-facing
  verdict — keep those on the default model.
- CREWAI_TIMEOUT_SECONDS / CREWAI_MAX_ITER bound a single crew task so a
  slow or looping Groq call can't blow up p99 latency unbounded. Every
  Agent built via registry._agent() gets these by default.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

# Per-task ceilings applied to every Agent (see registry._agent()). Keeps a
# stuck tool call or a model that won't stop iterating from turning into a
# multi-minute request.
CREWAI_TIMEOUT_SECONDS = float(os.getenv("CREWAI_TIMEOUT_SECONDS", "20"))
CREWAI_MAX_ITER = int(os.getenv("CREWAI_MAX_ITER", "6"))


# The same hard rules used by services/ai_client.GROUNDING_CONTRACT, restated
# here as agent backstory text. Any new agent in registry.py should append
# this to its backstory.
GROUNDING_CONTRACT = (
    "You are an analyst that answers STRICTLY from the inputs and tool outputs you receive. "
    "Hard rules: "
    "(1) Use ONLY facts present in the provided inputs and tool outputs. Do NOT use outside "
    "knowledge for numeric claims. "
    "(2) If a requested field cannot be supported by what you've been given, set its value to "
    "null and add an entry to `data_gaps` explaining what was missing. "
    "(3) Every rationale, pro, con, or risk item must be an object {text, source} where "
    "`source` names the input path or tool that backs the claim. No bare strings. "
    "(4) Output a top-level `confidence` field: 'low' | 'medium' | 'high'. 'high' only if "
    "every numeric field is directly present in the inputs/tools. "
    "(5) The user is unregistered with SEBI — describe rather than direct. Phrase outputs as "
    "educational signals, not actionable advice."
)


_llm_singleton = None
_llm_fast_singleton = None
_cache_breakpoint_bug_patched = False


def _patch_cache_breakpoint_bug() -> None:
    """Work around crewAIInc/crewAI#5886 (still open, PR #6355 unmerged as of
    crewai 1.15.14): crew_agent_executor.py unconditionally tags every message
    with a `cache_breakpoint` field meant for Anthropic-style prompt caching.
    Only the Anthropic-native LLM adapter strips it back out before sending —
    the LiteLLM-fallback path every non-native provider (Groq included) goes
    through does NOT, so the raw key reaches Groq's API and Groq's stricter
    message-schema validation rejects the whole request. Net effect without
    this patch: every crew kickoff against Groq throws, and both live crews
    silently fall back to the legacy path (caught by the routers' except).

    Workaround (from the issue thread): make mark_cache_breakpoint a no-op so
    the key is never added in the first place. `crew_agent_executor.py` does
    `from crewai.llms.cache import mark_cache_breakpoint` INSIDE the function
    that calls it, so patching the attribute on the `crewai.llms.cache` module
    before any crew runs is enough — that import re-resolves the name from the
    module's namespace on every call.

    Safe only because this app is Groq-only right now (base.py hard-requires
    GROQ_API_KEY). If/when the multi-provider fallback in the module docstring
    lands and Anthropic is added, this patch would also silently disable
    Anthropic prompt caching — scope it to non-Anthropic models at that point,
    or drop it entirely once #5886 ships in a released version.
    """
    global _cache_breakpoint_bug_patched
    if _cache_breakpoint_bug_patched:
        return
    import crewai.llms.cache as _crewai_cache
    _crewai_cache.mark_cache_breakpoint = lambda msg: msg
    _cache_breakpoint_bug_patched = True
    logger.info("Patched crewai cache_breakpoint bug (crewAIInc/crewAI#5886).")


def _build_llm(model: str):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY not set — agent crews are disabled. "
            "Either set it in .env or fall back to the legacy non-agent path."
        )

    try:
        from crewai import LLM  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "crewai not installed. pip install crewai crewai-tools (see requirements.txt)."
        ) from e

    _patch_cache_breakpoint_bug()

    llm = LLM(
        model=model,
        api_key=api_key,
        temperature=float(os.getenv("CREWAI_TEMPERATURE", "0.2")),
        timeout=CREWAI_TIMEOUT_SECONDS,
    )
    logger.info("CrewAI LLM initialized (model=%s, timeout=%ss).", model, CREWAI_TIMEOUT_SECONDS)
    return llm


def get_llm(fast: bool = False):
    """Return a CrewAI-compatible LLM. Lazy-imported so missing crewai doesn't break unrelated imports.

    fast=True returns a second singleton on CREWAI_FAST_MODEL (defaults to Groq's
    llama-3.1-8b-instant) for agents doing narrow extraction where the default
    model's extra latency isn't buying anything — see
    registry.make_narrative_extractor. Nothing changes for existing agents
    unless they explicitly opt in via `_agent(fast=True, ...)`.
    """
    global _llm_singleton, _llm_fast_singleton

    default_model = os.getenv("CREWAI_MODEL", "groq/" + os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"))

    if not fast:
        if _llm_singleton is None:
            _llm_singleton = _build_llm(default_model)
        return _llm_singleton

    if _llm_fast_singleton is None:
        fast_model = os.getenv("CREWAI_FAST_MODEL", "groq/llama-3.1-8b-instant")
        _llm_fast_singleton = _build_llm(fast_model)
    return _llm_fast_singleton


def prewarm() -> None:
    """Build the LLM singleton(s) eagerly. Call once from the FastAPI startup hook
    (see main.py) so SDK-import + client-construction cost is paid at boot instead
    of landing inside the first real request's time-to-first-response.

    Safe to call when crews are disabled — swallows and logs, never raises, so a
    missing GROQ_API_KEY or crewai install can't block app startup.
    """
    if not is_available():
        logger.info("agents.prewarm skipped — GROQ_API_KEY unset or crewai not installed.")
        return
    try:
        get_llm()
        get_llm(fast=True)
        logger.info("agents.prewarm complete — CrewAI LLM singletons ready.")
    except Exception:
        logger.exception("agents.prewarm failed — first agent request will pay cold-start cost.")


_crewai_importable: bool | None = None


def is_available() -> bool:
    """Cheap check the router can use to decide whether to take the agent path."""
    global _crewai_importable
    if not os.getenv("GROQ_API_KEY"):
        return False
    if _crewai_importable is None:
        try:
            import crewai  # noqa: F401
            _crewai_importable = True
        except ImportError:
            _crewai_importable = False
    return _crewai_importable
