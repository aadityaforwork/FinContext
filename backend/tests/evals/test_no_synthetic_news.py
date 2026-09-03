"""
The news path must never invent a catalyst, and must always date the ones it has
===============================================================================
Two changes pinned together, both from the FILATEX incident of 2026-09-03 (see
test_news_freshness.py for the fetch-side story).

1. NO SYNTHETIC FALLBACK. `data_ingestion.retrieve_context` used to end with
   "if fewer than 2 items came back, return NEWS_CORPUS[ticker]" — hand-written
   MVP demo headlines, handed to the LLM as though they were real reporting.
   It was near-unreachable while every source was unfiltered, because something
   always came back. Adding the freshness window to the per-ticker path made
   "fewer than 2 items" the ordinary case for any quiet stock, which would have
   promoted a dormant landmine to the default answer. An empty list is the
   honest result and the attribution surface already has `unexplained` +
   `data_gaps` for it.

2. AGE REACHES THE MODEL. The context builders shipped id / source / headline /
   snippet and dropped `published_date` on the floor. The date was fetched, used
   to sort, then discarded — so a four-month-old headline arrived in CONTEXT
   indistinguishable from this morning's, and no prompt could have preferred the
   recent one because the information was not there to prefer.

Deterministic — no network, no Supabase, no LLM.
"""

from __future__ import annotations

import time

import pytest

from app.services.marketdata import data_ingestion as di
from app.services.marketdata import news_sources as ns

DAY = 86400


@pytest.fixture(autouse=True)
def _clean_cache():
    di._news_cache.clear()
    yield
    di._news_cache.clear()


def _fresh(headline: str, age_days: float = 0.5) -> dict:
    return {
        "source": "Mint",
        "headline": headline,
        "snippet": headline,
        "url": "https://e.test/x",
        "published_date": time.strftime(
            "%Y-%m-%d %H:%M", time.gmtime(time.time() - age_days * DAY)
        ),
    }


# ---------------------------------------------------------------------------
# 1. No synthetic fallback
# ---------------------------------------------------------------------------
def test_a_ticker_with_no_fresh_news_gets_an_empty_list(monkeypatch):
    monkeypatch.setattr(ns, "fetch_for_ticker", lambda *a, **k: [])
    assert di.retrieve_context("FILATEX") == []


def test_seed_corpus_is_never_served_even_for_a_ticker_it_covers(monkeypatch):
    """REC is one of the five tickers NEWS_CORPUS actually has entries for, so
    this is the case the old fallback would have fired on."""
    from app.seed_data import NEWS_CORPUS

    assert NEWS_CORPUS.get("REC"), "test is pointless if the corpus lost this key"
    monkeypatch.setattr(ns, "fetch_for_ticker", lambda *a, **k: [])
    assert di.retrieve_context("REC") == []


def test_the_seed_corpus_is_not_even_imported():
    """Cheapest possible guard against someone reinstating the fallback."""
    import app.services.marketdata.data_ingestion as mod

    assert not hasattr(mod, "NEWS_CORPUS")


def test_a_single_fresh_item_is_returned_rather_than_discarded(monkeypatch):
    """The old gate was `if len(news) >= 2`, so exactly one real item was
    thrown away in favour of the seed corpus. One real headline beats both a
    fabricated one and nothing."""
    monkeypatch.setattr(ns, "fetch_for_ticker", lambda *a, **k: [_fresh("only item")])
    out = di.retrieve_context("TESTCO")
    assert [i["headline"] for i in out] == ["only item"]


def test_an_empty_result_is_not_cached(monkeypatch):
    """Empty is far more often a feed hiccup than a genuine absence of news.
    The upstream Google call is cached inside news_sources for 10 min, so
    retrying costs nothing on the common path."""
    calls = {"n": 0}

    def _flaky(*a, **k):
        calls["n"] += 1
        return [] if calls["n"] == 1 else [_fresh("recovered")]

    monkeypatch.setattr(ns, "fetch_for_ticker", _flaky)
    assert di.retrieve_context("TESTCO") == []
    assert [i["headline"] for i in di.retrieve_context("TESTCO")] == ["recovered"]


def test_a_non_empty_result_is_cached(monkeypatch):
    calls = {"n": 0}

    def _once(*a, **k):
        calls["n"] += 1
        return [_fresh("cached me")]

    monkeypatch.setattr(ns, "fetch_for_ticker", _once)
    di.retrieve_context("TESTCO")
    di.retrieve_context("TESTCO")
    assert calls["n"] == 1


# ---------------------------------------------------------------------------
# 2. Age reaches the model
# ---------------------------------------------------------------------------
def test_movers_context_news_items_carry_age_days(monkeypatch):
    """build_movers_context's per-holding news dict is what becomes
    holdings[i].news[j] — the exact path the FILATEX attribution cited."""
    from app.services.llm import grounding

    monkeypatch.setattr(
        grounding.data_ingestion, "retrieve_context",
        lambda *a, **k: [_fresh("six days old", age_days=6.0)],
    )
    raw = grounding.data_ingestion.retrieve_context("TESTCO", top_k=3)
    item = {
        "id": "TESTCO_news[0]",
        "source": raw[0].get("source"),
        "headline": raw[0].get("headline"),
        "snippet": (raw[0].get("snippet") or "")[:200],
        "age_days": ns.age_days(raw[0].get("published_date")),
    }
    assert item["age_days"] == 6


def test_the_context_builders_actually_set_the_field():
    """Guards the wiring, not the helper: both builders must emit `age_days`,
    since the prompt now instructs the model to read it and a silently missing
    key would read as 'undated' for every item."""
    import inspect

    from app.services.llm import grounding

    src = inspect.getsource(grounding)
    # build_movers_context (holdings[i].news[j]) and the morning brief's
    # _news_for both construct these dicts.
    assert src.count('"age_days": news_sources.age_days(') == 2


def test_movers_prompt_tells_the_model_what_to_do_with_age():
    """A field the prompt never mentions is only half the fix."""
    from app.routers.portfolio_intelligence import MOVERS_ATTRIBUTION_FALLBACK_PROMPT as P

    assert "age_days" in P
    assert "unexplained" in P
