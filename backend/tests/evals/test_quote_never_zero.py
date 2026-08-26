"""
A missing price must never surface as 0.0
========================================
THE BUG (2026-08-26): tickers showed ₹0.00 across the app. Not a fetch bug —
a *reporting* bug. `grounding._fetch_snapshot` gated its result on

    has_real_data = price > 0 or info.get("trailingPE") is not None or ...

while the comment directly above it said the test was "a price AND at least
one fundamental field". Yahoo rate-limits its quote endpoint far sooner than
quote_summary, so on a shared IP (Render) you routinely get NO price but a
cached marketCap — the `or` passed on that alone and emitted
`current_price: 0.0`. `fundamentals._quote_from_fast_info` was worse: it
returned 0.0 as its failure sentinel and `get_overview` wrote it straight out
with no guard at all.

Downstream, 0.0 is indistinguishable from a real price, so it rendered as a
confident ₹0.00 and produced a P&L equal to minus the entire position.

The rule these tests lock in: **unknown is None, never 0.** No listed equity
trades at zero, so a 0 from yfinance is always missing data.

Deterministic — no network, no Supabase, no LLM.
"""

from __future__ import annotations

import pytest

from app.services.marketdata import yf_safe


# ---------------------------------------------------------------------------
# Fakes shaped like the real yfinance failure modes
# ---------------------------------------------------------------------------
class _RaisingFastInfo:
    """yfinance's lazy FastInfo raises from __getattr__ on a failed lookup —
    it does not return None. Code that used `hasattr(fast, "last_price")`
    followed by `float(...)` fell into its except branch and produced 0.0."""

    def __getattr__(self, name):
        raise KeyError(name)


class _FakeTicker:
    def __init__(self, fast=None, hist=None, info=None):
        self._fast, self._hist, self._info = fast, hist, info or {}

    @property
    def fast_info(self):
        if self._fast is None:
            raise RuntimeError("quote endpoint rate limited")
        return self._fast

    @property
    def info(self):
        return self._info

    def history(self, period="5d"):
        if self._hist is None:
            raise RuntimeError("no history")
        return self._hist


class _Series(list):
    def tolist(self):
        return list(self)


class _FakeHist:
    def __init__(self, closes):
        self._closes = closes
        self.empty = not closes

    def __contains__(self, key):
        return key == "Close"

    def __getitem__(self, key):
        if key != "Close":
            raise KeyError(key)
        return _Series(self._closes)


class _GoodFastInfo:
    last_price = 1234.5
    previous_close = 1200.0
    market_cap = 4.5e12


# ---------------------------------------------------------------------------
# _num — the primitive the whole fix rests on
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad", [None, 0, 0.0, -1, -0.01, float("nan"), float("inf"), "", "abc", True, False])
def test_num_rejects_everything_that_is_not_a_real_price(bad):
    assert yf_safe._num(bad) is None


@pytest.mark.parametrize("good,expected", [(1, 1.0), (1234.5, 1234.5), ("99.25", 99.25)])
def test_num_accepts_real_prices(good, expected):
    assert yf_safe._num(good) == expected


def test_zero_is_rejected_not_passed_through():
    """The single most important assertion in this file. A 0 from yfinance
    always means 'no data' — no listed equity trades at zero."""
    assert yf_safe._num(0.0) is None


# ---------------------------------------------------------------------------
# read_quote
# ---------------------------------------------------------------------------
def test_read_quote_happy_path():
    price, prev, mcap = yf_safe.read_quote(_FakeTicker(fast=_GoodFastInfo()))
    assert (price, prev, mcap) == (1234.5, 1200.0, 4.5e12)


def test_read_quote_returns_none_not_zero_when_everything_fails():
    price, prev, mcap = yf_safe.read_quote(_FakeTicker(fast=None, hist=None))
    assert price is None and prev is None and mcap is None
    assert price != 0.0, "0.0 is the sentinel that caused the ₹0.00 bug"


def test_read_quote_falls_back_to_history_when_quote_endpoint_is_rate_limited():
    """The recovery path, and the reason this isn't merely a 'fail honestly'
    fix. Yahoo rate-limits quotes long before charts, so history usually still
    answers — market INDICES already had this fallback, individual stocks did
    not, which is why indices kept working while stocks went to zero."""
    tk = _FakeTicker(fast=None, hist=_FakeHist([100.0, 101.0, 105.5]))
    price, prev, _ = yf_safe.read_quote(tk)
    assert price == 105.5
    assert prev == 101.0


def test_read_quote_survives_fast_info_that_raises_per_attribute():
    tk = _FakeTicker(fast=_RaisingFastInfo(), hist=_FakeHist([50.0, 52.0]))
    price, prev, _ = yf_safe.read_quote(tk)
    assert price == 52.0


def test_read_quote_ignores_a_zero_close_in_history():
    tk = _FakeTicker(fast=None, hist=_FakeHist([0.0, 0.0]))
    assert yf_safe.read_quote(tk)[0] is None


def test_history_fallback_can_be_disabled():
    tk = _FakeTicker(fast=None, hist=_FakeHist([100.0]))
    assert yf_safe.read_quote(tk, allow_history_fallback=False)[0] is None


# ---------------------------------------------------------------------------
# The original bug, end to end
# ---------------------------------------------------------------------------
def test_snapshot_refuses_to_emit_a_priceless_row(monkeypatch):
    """THE regression test. Rate-limited quote + cached fundamentals used to
    yield {'current_price': 0.0, ...}. It must now yield {} instead."""
    from app.services.llm import grounding

    for cache in (grounding._snapshot_cache, grounding._snapshot_neg_perm,
                  grounding._snapshot_neg_transient):
        cache.pop("TCS", None)

    fundamentals_but_no_price = {
        "trailingPE": 28.4, "returnOnEquity": 0.31, "marketCap": 1.2e13,
        "fiftyTwoWeekHigh": 4592.0,
    }
    monkeypatch.setattr(
        grounding.yf, "Ticker",
        lambda _sym: _FakeTicker(fast=None, hist=None, info=fundamentals_but_no_price),
    )
    assert grounding._fetch_snapshot("TCS") == {}


def test_snapshot_still_works_when_only_history_answers(monkeypatch):
    """The flip side: a rate-limited quote must not lose a ticker we can
    still price from the chart endpoint."""
    from app.services.llm import grounding

    for cache in (grounding._snapshot_cache, grounding._snapshot_neg_perm,
                  grounding._snapshot_neg_transient):
        cache.pop("INFY", None)

    monkeypatch.setattr(
        grounding.yf, "Ticker",
        lambda _sym: _FakeTicker(
            fast=None, hist=_FakeHist([1500.0, 1520.0]),
            info={"trailingPE": 24.0, "marketCap": 6.3e12},
        ),
    )
    snap = grounding._fetch_snapshot("INFY")
    assert snap.get("current_price") == 1520.0
    assert snap.get("pe_ratio") == 24.0


def test_throttled_quote_is_cached_transient_not_delisted(monkeypatch):
    """The subtle half of the fix, and the one most likely to be undone.

    'No price' now short-circuits _fetch_snapshot — but a *throttled* quote
    must NOT be filed as delisted, because the delisted cache holds for 24h.
    Getting this wrong blanks a healthy ticker for a whole day after one bad
    second, which is worse than the ₹0.00 it replaced. Yahoo still serving
    fundamentals proves the symbol exists.
    """
    from app.services.llm import grounding

    for cache in (grounding._snapshot_cache, grounding._snapshot_neg_perm,
                  grounding._snapshot_neg_transient):
        cache.pop("TCS", None)

    monkeypatch.setattr(
        grounding.yf, "Ticker",
        lambda _sym: _FakeTicker(fast=None, hist=None,
                                 info={"trailingPE": 28.4, "marketCap": 1.2e13}),
    )
    assert grounding._fetch_snapshot("TCS") == {}
    assert "TCS" in grounding._snapshot_neg_transient, "should retry in 60s"
    assert "TCS" not in grounding._snapshot_neg_perm, "must NOT be filed as delisted for 24h"


def test_genuinely_dead_symbol_is_cached_permanent(monkeypatch):
    """The other side: nothing at all from Yahoo really is delisted, and
    should take the 24h TTL rather than being retried every 60s forever."""
    from app.services.llm import grounding

    for cache in (grounding._snapshot_cache, grounding._snapshot_neg_perm,
                  grounding._snapshot_neg_transient):
        cache.pop("DEADCO", None)

    monkeypatch.setattr(
        grounding.yf, "Ticker",
        lambda _sym: _FakeTicker(fast=None, hist=None, info={}),
    )
    assert grounding._fetch_snapshot("DEADCO") == {}
    assert "DEADCO" in grounding._snapshot_neg_perm


def test_overview_reports_unknown_price_as_none_not_zero(monkeypatch):
    """fundamentals.get_overview had no guard at all — 0.0 went straight into
    the payload the company page renders."""
    from app.services.marketdata import fundamentals

    fundamentals._overview_cache.pop("TCS", None)
    monkeypatch.setattr(
        fundamentals, "_resolve_ticker",
        lambda t: (_FakeTicker(fast=None, hist=None, info={"marketCap": 1.2e13}), "TCS", None),
    )
    out = fundamentals.get_overview("TCS")
    assert out["current_price"] is None
    assert out["current_price"] != 0.0
    # "flat today" is a stronger claim than "unknown" — it must not be made.
    assert out["change_percent"] is None
