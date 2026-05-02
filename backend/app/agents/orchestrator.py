"""
Agent orchestrator
==================
Thin layer that:
1. Wraps every crew kickoff in the persistent LLM cache (services/llm_cache).
2. Runs CrewAI crews on a thread pool so the synchronous CrewAI API doesn't
   block the FastAPI event loop.
3. Exposes a `run_parallel` helper for callers that want multiple crews
   running concurrently for the same request (e.g. Deep Dive + Catalyst Radar).

Crews themselves know nothing about caching — that's an orchestration concern,
not a reasoning one.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from app.services import llm_cache

logger = logging.getLogger(__name__)


async def run_cached(
    cache_key: str,
    ttl_seconds: int,
    builder: Callable[[], "object"],
    inputs: dict,
    scope: str = "global",
) -> dict:
    """
    Execute a CrewAI crew with cache-around. `builder` is a zero-arg function
    that returns a fresh Crew instance — passed lazily so we don't pay agent
    construction cost on cache hit.

    Returns the parsed dict that the crew's final task produced.
    """
    cached = await llm_cache.get(cache_key)
    if cached is not None:
        logger.info("crew cache hit: %s", cache_key)
        return cached

    crew = builder()
    # CrewAI's kickoff_async exists in recent versions; prefer it. Fall back to
    # running the sync kickoff on a thread.
    try:
        kickoff_async = getattr(crew, "kickoff_async", None)
        if kickoff_async is not None:
            output = await kickoff_async(inputs=inputs)
        else:
            output = await asyncio.to_thread(crew.kickoff, inputs=inputs)
    except Exception:
        logger.exception("crew kickoff failed for %s", cache_key)
        raise

    payload = _coerce_output(output)
    if payload:
        await llm_cache.set(cache_key, payload, ttl_seconds, scope)
    return payload


async def run_parallel(jobs: list[Awaitable[dict]]) -> list[dict]:
    """Run multiple cached-crew coroutines concurrently. Use for compose flows."""
    return await asyncio.gather(*jobs)


def _coerce_output(output) -> dict:
    """
    CrewAI's CrewOutput exposes .pydantic, .json_dict, .raw — pick whichever is set.
    We always want a plain dict on the way out, so the caller doesn't have to know
    which output format the final task chose.
    """
    if output is None:
        return {}

    pyd = getattr(output, "pydantic", None)
    if pyd is not None and hasattr(pyd, "model_dump"):
        return pyd.model_dump()

    json_dict = getattr(output, "json_dict", None)
    if isinstance(json_dict, dict):
        return json_dict

    raw = getattr(output, "raw", None)
    if isinstance(raw, str):
        import json as _json
        try:
            return _json.loads(raw)
        except _json.JSONDecodeError:
            logger.warning("crew output was non-JSON string; returning empty dict")
            return {}

    if isinstance(output, dict):
        return output

    logger.warning("crew output type %s not recognized", type(output))
    return {}
