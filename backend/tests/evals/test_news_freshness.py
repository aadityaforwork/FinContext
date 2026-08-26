"""
A news feed must never serve old news, and must never eat its own sort key
=========================================================================
Two bugs found together on 2026-08-26. They are independent, but the second
one hid the first, so they are pinned together.

BUG 1 — stale content at HTTP 200. Moneycontrol's `MCtopnews.xml` was serving
entries dated 2016-10-05 ("Sensex, Nifty wobbly; Hind Zinc, SBI, Force...")
and `business.xml` entries from 2024-04-23. The request succeeded, the XML
parsed, entries came back — every guard in `news_sources` passed it, because
every guard was about *transport*. Those headlines went into
`grounding.build_market_context` as current market context, which makes the
model narrate decade-old news as today's (AGENTS.md rule 1).

BUG 2 — the freshness sort deleted the field it sorts on. `fetch_feed`
returned its cached list directly, and `fetch_india_market_pool` ended with
`for it in items: it.pop("_ts", None)`. Those were the same dict objects. So
the first pool call per 10-minute TTL stripped `_ts` from the cache and every
call after it sorted `0` against `0` — the sort became a no-op and ordering
degraded to thread-completion order. Measured: `_ts` on 12/12 items after
`fetch_feed`, 0/12 after one pool call; three consecutive pool calls returned
today's headlines, then 2016's, then 2016's.

Together: most requests inside any given TTL window were ranking stale items
to the top. Fixing either alone would have left the other live.

Deterministic — no network, no Supabase, no LLM.
"""

from __future__ import annotations

import time

import pytest

from app.services.marketdata import news_sources as ns

DAY = 86400


@pytest.fixture(autouse=True)
def _clean_caches():
    """These caches are module-level and TTL'd, so tests would otherwise leak
    into each other through them."""
    ns._feed_cache.clear()
    ns._feed_neg_cache.clear()
    ns._feed_logged_failure.clear()
    ns._feed_logged_stale.clear()
    yield
    ns._feed_cache.clear()
    ns._feed_neg_cache.clear()


def _item(headline: str, age_days: float, source: str = "Test Desk") -> dict:
    return {
        "source": source,
        "category": "markets",
        "headline": headline,
        "snippet": headline,
        "url": f"https://example.test/{headline.replace(' ', '-')}",
        "published_date": "",
        "_ts": time.time() - age_days * DAY,
    }


# ---------------------------------------------------------------------------
# BUG 1 — _drop_stale
# ---------------------------------------------------------------------------
def test_todays_news_survives():
    items = [_item("fresh", 0.1)]
    assert len(ns._drop_stale(items, "Test Desk", "u")) == 1


def test_the_actual_moneycontrol_item_is_dropped():
    """The literal headline that was live in the pool, at its real age."""
    stale = _item("Sensex, Nifty wobbly; Hind Zinc, SBI, Force", age_days=3613)
    assert ns._drop_stale([stale], "Moneycontrol", "u") == []


@pytest.mark.parametrize("age_days", [8, 30, 365, 730, 3613])
def test_anything_past_the_window_is_dropped(age_days):
    assert ns._drop_stale([_item("old", age_days)], "d", "u") == []


@pytest.mark.parametrize("age_days", [0, 1, 3, 6.9])
def test_anything_inside_the_window_is_kept(age_days):
    assert len(ns._drop_stale([_item("ok", age_days)], "d", "u")) == 1


def test_future_dated_items_are_dropped_too():
    """A skewed publisher clock pins its items to the top of every freshness
    sort forever — the same failure as stale content, mirrored."""
    assert ns._drop_stale([_item("tomorrow", -3)], "d", "u") == []


def test_small_future_skew_is_tolerated():
    """Timezone sloppiness is not fabrication."""
    assert len(ns._drop_stale([_item("just ahead", -0.5)], "d", "u")) == 1


def test_undated_items_are_kept_not_dropped():
    """Deliberate. We can't prove an undated item is stale, and dropping them
    would silently zero out any feed that changes date format. They sort to
    the bottom anyway, and the count gets logged."""
    undated = _item("no date", 0)
    undated["_ts"] = 0.0
    assert len(ns._drop_stale([undated], "d", "u")) == 1


def test_a_partly_stale_feed_keeps_its_good_items():
    """Moneycontrol's business.xml had both. Dropping the whole feed on one
    bad entry would lose real coverage."""
    items = [_item("fresh", 0.5), _item("ancient", 3613), _item("also fresh", 2)]
    kept = ns._drop_stale(items, "d", "u")
    assert [k["headline"] for k in kept] == ["fresh", "also fresh"]


def test_stale_drop_is_logged_once_per_feed(caplog):
    """Silent dropping would replace one invisible failure with another."""
    with caplog.at_level("WARNING"):
        ns._drop_stale([_item("old", 3613)], "Moneycontrol", "u1")
        ns._drop_stale([_item("old", 3613)], "Moneycontrol", "u1")
    hits = [r for r in caplog.records if "untrustworthy dates" in r.message]
    assert len(hits) == 1, "should log once per process, not once per fetch"


def test_stale_and_dead_are_logged_separately():
    """A feed serving 2016 content is a different operational fact from a feed
    that won't respond; one must not mask the other."""
    ns._drop_stale([_item("old", 3613)], "Moneycontrol", "u1")
    assert "u1" in ns._feed_logged_stale
    assert "u1" not in ns._feed_logged_failure


# ---------------------------------------------------------------------------
# BUG 2 — cache aliasing
# ---------------------------------------------------------------------------
def _install_feed(monkeypatch, items):
    """Put items in the cache as if a fetch had produced them."""
    url = ns.INDIAN_MARKET_FEEDS[0][0]
    ns._feed_cache[url] = list(items)
    # Every other feed returns nothing, so the pool is exactly `items`.
    monkeypatch.setattr(
        ns, "INDIAN_MARKET_FEEDS", [ns.INDIAN_MARKET_FEEDS[0]]
    )
    return url


def test_fetch_feed_does_not_hand_out_the_cached_objects(monkeypatch):
    url = _install_feed(monkeypatch, [_item("a", 0.1)])
    got = ns.fetch_feed(url, "Test Desk", "markets", 12)
    got[0]["_ts"] = 0
    got[0]["injected"] = True
    assert ns._feed_cache[url][0]["_ts"] != 0
    assert "injected" not in ns._feed_cache[url][0]


def test_pool_does_not_destroy_the_sort_key_in_the_cache(monkeypatch):
    """THE regression test for bug 2."""
    url = _install_feed(monkeypatch, [_item(f"h{i}", i * 0.1) for i in range(12)])
    assert all("_ts" in it for it in ns._feed_cache[url])
    ns.fetch_india_market_pool(n=12)
    survivors = sum(1 for it in ns._feed_cache[url] if "_ts" in it)
    assert survivors == 12, "one pool call wiped the sort key out of the cache"


def test_pool_ordering_is_stable_across_repeated_calls(monkeypatch):
    """The user-visible symptom: call 1 returned today's news, calls 2 and 3
    returned 2016's, because the sort had nothing left to sort on."""
    _install_feed(monkeypatch, [
        _item("oldest-but-still-valid", 6),
        _item("newest", 0.1),
        _item("middle", 2),
    ])
    runs = [
        [i["headline"] for i in ns.fetch_india_market_pool(n=12)]
        for _ in range(3)
    ]
    assert runs[0] == ["newest", "middle", "oldest-but-still-valid"]
    assert runs[0] == runs[1] == runs[2], f"ordering drifted across calls: {runs}"


def test_pool_still_strips_the_private_ts_from_what_it_returns(monkeypatch):
    """`_ts` is internal — the fix must not leak it to API consumers."""
    _install_feed(monkeypatch, [_item("a", 0.1)])
    assert all("_ts" not in it for it in ns.fetch_india_market_pool(n=12))


def test_google_results_do_not_leak_between_tickers(monkeypatch):
    """`data_ingestion.retrieve_context` writes `relevance_score` onto whatever
    it gets back; that used to land in the shared cache, so one ticker's
    ranking bled into the next ticker's items."""
    key = "gnews|Q|en-IN|IN|IN:en"
    ns._feed_cache[key] = [{"source": "X", "headline": "h", "url": ""}]
    first = ns.google_news_for_query("Q")
    first[0]["relevance_score"] = 0.95
    second = ns.google_news_for_query("Q")
    assert "relevance_score" not in second[0]


# ---------------------------------------------------------------------------
# The two bugs interacting
# ---------------------------------------------------------------------------
def test_stale_items_cannot_reach_the_pool_even_once(monkeypatch):
    """Bug 2 made bug 1 intermittent — fresh on the first call, stale after.
    Filtering happens before caching, so there is no call number at which the
    2016 items appear."""
    url = ns.INDIAN_MARKET_FEEDS[0][0]
    monkeypatch.setattr(ns, "INDIAN_MARKET_FEEDS", [ns.INDIAN_MARKET_FEEDS[0]])
    ns._feed_cache[url] = ns._drop_stale(
        [_item("fresh", 0.1), _item("from 2016", 3613)], "Moneycontrol", url
    )
    for _ in range(4):
        heads = [i["headline"] for i in ns.fetch_india_market_pool(n=12)]
        assert heads == ["fresh"]
