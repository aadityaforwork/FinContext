"""
yf_safe — defensive yfinance wrapper
====================================
yfinance has two failure modes that destroy Context Engine wall time:

  1. Network calls have no externally-controllable timeout. A slow Yahoo
     response can block a thread for 15-30 seconds.
  2. Delisted / unknown tickers fail predictably with "No data found" or
     HTTP 404 — but yfinance internally retries multiple endpoints before
     giving up, costing ~10s per attempt. Our 60s negative TTL means we
     re-pay that cost every minute.

This module fixes both:

  • run_with_timeout(fn, *args, timeout_s=4, **kwargs)
        executes `fn` on a small shared thread pool with a hard timeout.
        Returns (result, ok). If the call exceeds timeout_s, the worker
        thread is left to finish in the background (Python cannot kill
        threads) but the caller gets ok=False immediately.

  • classify_error(exc, output) -> "permanent" | "transient" | None
        looks at the exception (and optionally a None/empty result) and
        decides whether the symbol is permanently bad (delisted, unknown)
        or just having a temporary hiccup. Callers use this to pick the
        right negative-cache TTL (24h vs 60s).

  • TIMEOUT_S — default per-call ceiling (4 seconds). Tuned so 12 parallel
    workers fanning out across a 40-stock portfolio finish in <20s even if
    a few tickers are slow.

This file is deliberately tiny and dependency-free so it can be imported
from any service without circular imports.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from typing import Any, Callable, Literal

logger = logging.getLogger(__name__)

# Shared executor — small pool, daemon threads so they don't block shutdown.
# Sized just above the movers pool (12) so a full movers fan-out still gets a
# worker here, plus headroom for the news/watchlist/portfolio endpoints that
# also fan out 12 threads in parallel. Was 32 — dropped to 16 to save ~150 MB
# of idle-thread overhead on Render Starter's 512 MB cap.
_yf_executor = ThreadPoolExecutor(max_workers=16, thread_name_prefix="yf-safe")

# Per-call wall ceiling. Beyond this, yfinance is almost certainly stuck on
# a slow Yahoo response or a delisted-symbol retry storm. Bail and cache.
TIMEOUT_S: float = 4.0

# Phrases that appear in yfinance/Yahoo error messages or stderr when a
# symbol is genuinely delisted / never existed. Match is case-insensitive
# substring; we keep it conservative — false-positive "permanent" classify
# means we'd cache a transient error for 24h, which is the more painful
# direction. Anything we're unsure about stays "transient".
_PERMANENT_MARKERS = (
    "possibly delisted",
    "no data found",
    "symbol may be delisted",
    "no earnings dates found",
    "quote not found",
    "404",
    "not found for symbol",
)


def run_with_timeout(
    fn: Callable[..., Any],
    *args,
    timeout_s: float = TIMEOUT_S,
    **kwargs,
) -> tuple[Any, bool]:
    """Run `fn(*args, **kwargs)` with a hard wall-clock timeout.

    Returns (result, ok):
      ok=True   — fn returned within budget; result is its return value
      ok=False  — fn timed out OR raised. result is None on timeout, or
                  the exception object if it raised within the budget.

    The worker thread is NOT killed on timeout (Python doesn't support
    that). It will finish whenever yfinance gives up. The cost is one
    leaked thread for a few extra seconds — acceptable given the executor
    pool is sized generously.
    """
    fut = _yf_executor.submit(fn, *args, **kwargs)
    try:
        return fut.result(timeout=timeout_s), True
    except FutTimeout:
        return None, False
    except Exception as e:
        return e, False


def classify_error(exc: Exception | None, result: Any = "__sentinel__") -> Literal["permanent", "transient"]:
    """Decide whether a yfinance failure is delisted-permanent or transient.

    Permanent → callers should use a 24h negative TTL.
    Transient → callers should use 60s so we retry promptly after a hiccup.

    Heuristics:
      • Exception message contains any _PERMANENT_MARKERS substring
      • Or the result is explicitly None/empty (caller passed it in)
        AND no exception was raised — that's almost always "no such symbol"
    """
    msg = ""
    if exc is not None:
        try:
            msg = str(exc).lower()
        except Exception:
            msg = ""
    # yfinance also prints its delisted warnings via stderr, not always as
    # the exception message — but when the symbol is unknown the call still
    # raises an HTTPError or returns empty. We can't see stderr from here,
    # so we rely on what we have.
    if msg and any(marker in msg for marker in _PERMANENT_MARKERS):
        return "permanent"
    if result != "__sentinel__":
        # Caller is telling us the result was empty/None — strong delisted signal.
        if result is None or (hasattr(result, "empty") and getattr(result, "empty", False)):
            return "permanent"
    return "transient"


# Cache-TTL constants — callers import these so the policy lives in one place.
NEG_TTL_PERMANENT_S: int = 60 * 60 * 24       # 24 hours
NEG_TTL_TRANSIENT_S: int = 60                 # 1 minute
