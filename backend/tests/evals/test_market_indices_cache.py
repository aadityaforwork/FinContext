"""
The market-indices strip must cache, and must fetch in parallel
===============================================================
TWO BUGS, both in get_market_indices(), both found while timing the
ingestion pipeline on 2026-09-02.

BUG 1 — the 3-minute cache never worked. The function opened with

    cache_key = "market_indices"
    if cache_key in _index_cache: ...

then REUSED that same local inside its per-index loop:

    for label, symbol in INDEX_MAP.items():
        cache_key = f"idx_{symbol}"      # <-- shadows the outer name

so the closing `_index_cache[cache_key] = results` filed the whole list
under "idx_INR=X" (the last symbol in INDEX_MAP). The lookup at the top
never found anything, and the entry that WAS written was never read by
anyone. Dead from the day it was written — every dashboard load re-fetched
all four indices from Yahoo.

BUG 2 — it fetched serially. Every other fan-out in the ingestion path runs
concurrently; this one ran `for symbol in ...` with a 5s ceiling per call,
so four indices could cost 20s of wall time on the dashboard's critical
path. Measured 10.0s cold on a laptop, and Render's shared IP is slower.

After the fix, measured on the same laptop: cold 10.01s -> 1.30s, warm
0.844s -> 0.000s.

Deterministic — no network, no Supabase, no LLM.
"""

from __future__ import annotations

import threading
import time

import pytest

from app.services.marketdata import market_data as md


@pytest.fixture(autouse=True)
def _clear_caches():
    md._index_cache.clear()
    md._index_neg_perm.clear()
    md._index_neg_transient.clear()
    yield
    md._index_cache.clear()
    md._index_neg_perm.clear()
    md._index_neg_transient.clear()


class _FakeFetch:
    """Stands in for yf_safe.run_with_timeout, recording when each call ran."""

    def __init__(self, delay=0.0, fail_symbols=(), price=100.0):
        self.delay = delay
        self.fail_symbols = set(fail_symbols)
        self.price = price
        self.spans = []
        self.symbols = []
        self._lock = threading.Lock()

    def __call__(self, fn, symbol, timeout_s=5.0, **kw):
        start = time.monotonic()
        time.sleep(self.delay)
        end = time.monotonic()
        with self._lock:
            self.spans.append((start, end))
            self.symbols.append(symbol)
        if symbol in self.fail_symbols:
            return (None, False)          # timed out
        return ((self.price, self.price * 0.99), True)


@pytest.fixture
def faked(monkeypatch):
    def _apply(fake):
        monkeypatch.setattr(md.yf_safe, "run_with_timeout", fake)
        return fake
    return _apply


# ---------------------------------------------------------------------------
# BUG 1 — the cache
# ---------------------------------------------------------------------------
def test_second_call_is_a_cache_hit(faked):
    fake = faked(_FakeFetch())

    first = md.get_market_indices()
    calls_after_first = len(fake.symbols)
    second = md.get_market_indices()

    assert calls_after_first == len(md.INDEX_MAP)
    assert len(fake.symbols) == calls_after_first, "second call re-fetched — cache missed"
    assert second is first


def test_result_is_stored_under_the_key_the_lookup_uses(faked):
    """The exact shape of the bug: written under one key, read under another."""
    faked(_FakeFetch())
    md.get_market_indices()

    assert md._ALL_INDICES_KEY in md._index_cache, (
        f"result not filed under {md._ALL_INDICES_KEY!r}; "
        f"cache holds {list(md._index_cache.keys())}"
    )
    # And nothing per-symbol should have leaked into the positive cache.
    stray = [k for k in md._index_cache if k != md._ALL_INDICES_KEY]
    assert not stray, f"per-index keys leaked into the whole-list cache: {stray}"


def test_per_index_negative_keys_do_not_collide_with_the_list_key(faked):
    faked(_FakeFetch(fail_symbols=["^NSEI"]))
    md.get_market_indices()

    assert "idx_^NSEI" in md._index_neg_transient
    assert md._ALL_INDICES_KEY not in md._index_neg_transient
    assert md._ALL_INDICES_KEY not in md._index_neg_perm


# ---------------------------------------------------------------------------
# BUG 2 — parallelism
# ---------------------------------------------------------------------------
def test_indices_are_fetched_concurrently(faked):
    """Four 0.3s fetches must finish in well under 1.2s, and their
    [start, end] windows must overlap. Wall time alone could pass by luck on
    a fast machine; genuinely serial calls can never overlap."""
    delay = 0.3
    fake = faked(_FakeFetch(delay=delay))

    t0 = time.monotonic()
    md.get_market_indices()
    elapsed = time.monotonic() - t0

    n = len(md.INDEX_MAP)
    serial = delay * n
    assert elapsed < serial * 0.6, (
        f"took {elapsed:.2f}s; serial would be ~{serial:.2f}s — still fetching one at a time"
    )
    assert max(s for s, _ in fake.spans) < min(e for _, e in fake.spans), (
        "no two index fetches were ever in flight at the same time"
    )


def test_row_order_matches_index_map(faked):
    """UniverseRail renders the strip positionally, so order is load-bearing.
    as_completed would break this; ex.map preserves it."""
    faked(_FakeFetch(delay=0.05))
    rows = md.get_market_indices()
    assert [r["label"] for r in rows] == list(md.INDEX_MAP.keys())


def test_order_holds_even_when_some_fetches_are_slower(faked):
    """The failing symbol returns fastest here — if results were collected in
    completion order, it would jump the queue."""

    class _Staggered(_FakeFetch):
        def __call__(self, fn, symbol, timeout_s=5.0, **kw):
            time.sleep(0.0 if symbol == "^BSESN" else 0.15)
            if symbol == "^BSESN":
                return (None, False)
            return ((100.0, 99.0), True)

    faked(_Staggered())
    rows = md.get_market_indices()
    assert [r["label"] for r in rows] == list(md.INDEX_MAP.keys())
    assert rows[list(md.INDEX_MAP).index("SENSEX")]["value"] == "—"


# ---------------------------------------------------------------------------
# What gets cached
# ---------------------------------------------------------------------------
def test_all_blank_result_is_not_cached(faked):
    """Pinning an all-dashes strip for 3 minutes would outlive the 60s
    negative cache that already prevents a retry storm."""
    fake = faked(_FakeFetch(fail_symbols=md.INDEX_MAP.values()))

    rows = md.get_market_indices()
    assert all(r["value"] == "—" for r in rows)
    assert md._ALL_INDICES_KEY not in md._index_cache

    md._index_neg_transient.clear()   # pretend the 60s window elapsed
    before = len(fake.symbols)
    md.get_market_indices()
    assert len(fake.symbols) > before, "a fully-failed strip must be retried, not served from cache"


def test_partial_result_is_cached(faked):
    """One working index is still worth serving — don't throw the whole
    strip away because one symbol is down."""
    faked(_FakeFetch(fail_symbols=["^NSEI", "^BSESN"]))

    rows = md.get_market_indices()
    assert any(r["value"] != "—" for r in rows)
    assert md._ALL_INDICES_KEY in md._index_cache


def test_negative_cached_symbol_is_skipped_not_refetched(faked):
    fake = faked(_FakeFetch())
    md._index_neg_perm["idx_^NSEI"] = True

    rows = md.get_market_indices()

    assert "^NSEI" not in fake.symbols, "a negative-cached symbol must not be fetched"
    assert rows[list(md.INDEX_MAP).index("NIFTY 50")]["value"] == "—"


# ---------------------------------------------------------------------------
# The shadowing pattern must not come back
# ---------------------------------------------------------------------------
def test_source_does_not_reassign_the_cache_key_variable():
    """Guards the exact typo. The whole-list key is a module constant now, so
    a future loop variable can't quietly take its name."""
    import inspect

    src = inspect.getsource(md.get_market_indices)
    assert 'cache_key = f"idx_' not in src, (
        "the per-index key is being assigned to a variable named cache_key again — "
        "that is how the whole-list cache got clobbered the first time"
    )
    assert "_ALL_INDICES_KEY" in src
