"""
A timeout must never be cached as "delisted"
============================================
THE BUG (2026-09-01): the whole ticker universe went blank in production
while every ticker loaded fine on a laptop.

Twelve call sites across routers/ and services/ spelled their negative-cache
classification inline, identically:

    result, ok = yf_safe.run_with_timeout(_inner, sym, timeout_s=5.0)
    if not ok:
        exc = result if isinstance(result, Exception) else None
        kind = yf_safe.classify_error(exc, None if exc is None else "__sentinel__")

`run_with_timeout` has two failure legs and they mean opposite things:

    ok=False, result is an Exception  -> the call raised. Message is evidence.
    ok=False, result is None          -> the call TIMED OUT. Says nothing
                                         about the symbol, only about our
                                         wall clock.

On the timeout leg the idiom above passes `result=None` into
`classify_error`, whose documented contract reads a None result as "the
caller saw an empty response" — its delisted signal. So every timeout came
back "permanent" and got negative-cached for **24 hours**.

Why production only: locally Yahoo answers well inside the budget, so the
timeout leg never fires. In production it fires constantly — higher RTT from
a shared cloud IP, and ~96 outer fan-out workers across nine pools all
bottlenecking on yf_safe's 16-slot executor, so the per-call budget gets
eaten by queue wait before yfinance is even called. Worse, a timed-out call
keeps running (Python can't kill threads), holding its slot and pushing the
next batch further past the deadline. One bad minute blackholes every ticker
for a day.

It was also invisible: most call sites guarded their log line behind
`if exc is not None`, which is never true on a timeout.

The rule these tests lock in: **a timeout is transient, always.** A delisted
ticker fails fast; it does not hang.

Deterministic — no network, no Supabase, no LLM.
"""

from __future__ import annotations

import time

import pytest

from app import nse_universe
from app.routers import portfolio, stocks, watchlist
from app.services.marketdata import market_data, yf_safe


# ---------------------------------------------------------------------------
# classify_failure — the unit that call sites now share
# ---------------------------------------------------------------------------
def test_timeout_leg_is_transient():
    """result=None means run_with_timeout hit the wall clock. Never permanent."""
    assert yf_safe.classify_failure(None) == "transient"


def test_delisted_exception_is_still_permanent():
    """The exception leg must keep pattern-matching — that half was correct."""
    exc = Exception("MSFTX.NS: possibly delisted; no price data found")
    assert yf_safe.classify_failure(exc) == "permanent"


def test_unknown_exception_is_transient():
    """Anything we can't positively identify as delisted stays cheap to retry."""
    assert yf_safe.classify_failure(ConnectionResetError("connection reset")) == "transient"


def test_rate_limit_exception_is_transient():
    """The exact shape that poisoned 41 real tickers once already."""
    exc = Exception("429 Too Many Requests: Yahoo rate limit")
    assert yf_safe.classify_failure(exc) == "transient"


@pytest.mark.parametrize("marker", yf_safe._PERMANENT_MARKERS)
def test_every_permanent_marker_still_classifies_permanent(marker):
    assert yf_safe.classify_failure(Exception(f"boom: {marker}")) == "permanent"


# ---------------------------------------------------------------------------
# End-to-end through run_with_timeout — the real integration
# ---------------------------------------------------------------------------
def test_real_timeout_classifies_transient():
    """The regression itself: run something slower than its budget and confirm
    the result is a 60s cache entry, not a 24h one."""

    def _slow():
        time.sleep(1.0)
        return ("never gets here",)

    result, ok = yf_safe.run_with_timeout(_slow, timeout_s=0.05)
    assert ok is False
    assert result is None, "timeout leg must yield a None result, not an exception"

    kind = yf_safe.classify_failure(result)
    assert kind == "transient"

    ttl = yf_safe.NEG_TTL_PERMANENT_S if kind == "permanent" else yf_safe.NEG_TTL_TRANSIENT_S
    assert ttl == yf_safe.NEG_TTL_TRANSIENT_S
    assert ttl <= 60, "a slow Yahoo response must not blackhole a ticker for hours"


def test_raising_call_still_reaches_the_exception_leg():
    def _boom():
        raise ValueError("no data found for symbol")

    result, ok = yf_safe.run_with_timeout(_boom, timeout_s=5.0)
    assert ok is False
    assert isinstance(result, ValueError)
    assert yf_safe.classify_failure(result) == "permanent"


def test_executor_permit_lives_until_timed_out_work_really_finishes(monkeypatch):
    """Returning to the caller must not admit another job while Python's
    unkillable timed-out worker is still occupying the executor."""
    state = {"released": False, "callback": None}

    class Permit:
        def acquire(self, timeout):
            return True

        def release(self):
            state["released"] = True

    class Future:
        def add_done_callback(self, callback):
            state["callback"] = callback

        def result(self, timeout):
            raise yf_safe.FutTimeout

    class Executor:
        def submit(self, *args, **kwargs):
            return Future()

    monkeypatch.setattr(yf_safe, "_yf_capacity", Permit())
    monkeypatch.setattr(yf_safe, "_yf_executor", Executor())

    result, ok = yf_safe.run_with_timeout(lambda: None, timeout_s=0.01)

    assert (result, ok) == (None, False)
    assert state["released"] is False
    state["callback"](None)
    assert state["released"] is True


# ---------------------------------------------------------------------------
# describe_failure — timeouts must stop being silent
# ---------------------------------------------------------------------------
def test_describe_failure_renders_the_timeout_leg():
    """The old `if exc is not None` guard logged nothing for the single most
    common production failure. describe_failure always returns something."""
    msg = yf_safe.describe_failure(None, 5.0)
    assert msg
    assert "timed out" in msg
    assert "5" in msg


def test_describe_failure_renders_exceptions_with_type():
    msg = yf_safe.describe_failure(ValueError("bad symbol"), 5.0)
    assert "ValueError" in msg
    assert "bad symbol" in msg


def test_nse_probe_timeout_uses_transient_cache(monkeypatch):
    """The uncurated-ticker search probe is also a production ticker path.
    It used to collapse timeout and returned-empty into one 30-minute miss."""
    ticker = "TIMEOUTTEST"
    nse_universe._probe_cache.clear()
    nse_universe._probe_neg_perm.clear()
    nse_universe._probe_neg_transient.clear()
    monkeypatch.setattr(yf_safe, "run_with_timeout", lambda *a, **kw: (None, False))

    assert nse_universe._probe_yf_ticker(ticker) is None
    assert ticker in nse_universe._probe_neg_transient
    assert ticker not in nse_universe._probe_neg_perm


def test_nse_probe_returned_empty_uses_permanent_cache(monkeypatch):
    ticker = "EMPTYTEST"
    nse_universe._probe_cache.clear()
    nse_universe._probe_neg_perm.clear()
    nse_universe._probe_neg_transient.clear()
    monkeypatch.setattr(yf_safe, "run_with_timeout", lambda *a, **kw: (None, True))

    assert nse_universe._probe_yf_ticker(ticker) is None
    assert ticker in nse_universe._probe_neg_perm
    assert ticker not in nse_universe._probe_neg_transient


@pytest.mark.parametrize(
    "getter,positive_cache,permanent_cache,transient_cache,cache_key",
    [
        (portfolio._get_live_price, portfolio._price_cache,
         portfolio._price_neg_perm, portfolio._price_neg_transient, "TCS"),
        (watchlist._get_price, watchlist._price_cache,
         watchlist._price_neg_perm, watchlist._price_neg_transient, "TCS"),
        (stocks._get_quote, stocks._browse_cache,
         stocks._browse_neg_perm, stocks._browse_neg_transient, "browse_TCS"),
        (market_data.get_live_quote, market_data._price_cache,
         market_data._price_neg_perm, market_data._price_neg_transient, "quote_TCS"),
    ],
)
def test_resolved_quote_with_empty_yahoo_response_retries_soon(
    monkeypatch, getter, positive_cache, permanent_cache, transient_cache, cache_key,
):
    """A valid resolved NSE symbol can return empty when a shared cloud IP is
    throttled. That ambiguity must not become a 24-hour delisted verdict."""
    for cache in (positive_cache, permanent_cache, transient_cache):
        cache.clear()
    monkeypatch.setattr(yf_safe, "run_with_timeout", lambda *a, **kw: (None, True))

    getter("TCS")

    assert cache_key in transient_cache
    assert cache_key not in permanent_cache


@pytest.mark.parametrize(
    "quote_reader",
    [portfolio._fetch_price_inner, watchlist._fetch_inner, stocks._quote_inner],
)
def test_user_facing_quote_paths_use_chart_fallback(monkeypatch, quote_reader):
    monkeypatch.setattr(yf_safe, "read_quote", lambda ticker: (105.0, 100.0, None))
    assert quote_reader("TCS.NS") == (105.0, 5.0)


# ---------------------------------------------------------------------------
# The idiom itself must not come back
# ---------------------------------------------------------------------------
def test_no_call_site_reintroduces_the_broken_idiom():
    """Guards against a copy-paste revival. The bug's whole character was that
    it lived in twelve identical hand-rolled copies rather than one function,
    so a thirteenth copy would silently restore it."""
    import pathlib

    app_dir = pathlib.Path(yf_safe.__file__).resolve().parents[2]
    offenders = []
    for path in app_dir.rglob("*.py"):
        if "__pycache__" in path.parts or path.name == "yf_safe.py":
            continue
        text = path.read_text(encoding="utf-8")
        if 'classify_error(exc, None if exc is None else "__sentinel__")' in text:
            offenders.append(str(path.relative_to(app_dir)))

    assert not offenders, (
        "These call sites re-introduced the timeout-as-permanent bug. Use "
        "yf_safe.classify_failure(result) instead:\n  " + "\n  ".join(offenders)
    )
