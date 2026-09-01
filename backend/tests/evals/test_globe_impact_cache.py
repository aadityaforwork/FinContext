"""
Globe portfolio-impact must not re-pay the LLM for identical input
=================================================================
The headlines feeding `/api/global-news/portfolio-impact` are themselves
cached for 5 minutes (`_news_cache`), so clicking back to a country you
already opened handed the model a byte-identical CONTEXT and paid the full
call again. Measured live against gpt-4o-mini on 2026-09-01: 2.3s with no
portfolio, 5.2s with one.

Same TTL as the news cache on purpose — a longer one would outlive the
headlines the answer describes.

WHAT THIS FILE IS NOT. An earlier attempt at this endpoint sharded the six
headlines into six concurrent LLM calls, on the theory that one call writing
six headlines' worth of analysis decodes ~6x as long. Measurement killed it:
this task SUMMARISES rather than annotates, so output is a fixed size no
matter how many headlines go in — 1 headline produced 677 output tokens,
6 produced 270, and the 6-headline call was *faster* (5.2s vs 10.2s). Six
calls each pay the full ~2s fixed overhead and re-send the whole prompt, so
sharding cost 4.7x more and ran slower. Don't re-add it here. (Sharding does
pay on the news-feed annotation call, where output genuinely grows per item —
different shape, measured separately.)

Deterministic — no network, no Supabase, no real LLM.
"""

from __future__ import annotations

import asyncio

import pytest

from app.routers import global_news as gn


@pytest.fixture(autouse=True)
def _clear_cache():
    gn._impact_cache.clear()
    yield
    gn._impact_cache.clear()


class _Counter:
    def __init__(self):
        self.n = 0

    def __call__(self, task, context, schema, max_tokens=2048, *a, **kw):
        self.n += 1
        return {
            "impact_summary": "summary",
            "affected_stocks": [
                {"ticker": "RELIANCE", "impact": "negative",
                 "reason": {"text": "oil", "source": "headlines[0]"}}
            ],
            "confidence": "medium",
            "data_gaps": [],
        }


@pytest.fixture
def counted(monkeypatch):
    c = _Counter()
    monkeypatch.setattr(gn.ai_client, "is_available", lambda: True)
    monkeypatch.setattr(gn.ai_client, "generate_grounded_json", c)
    return c


def _call(headlines, tickers=None, country="US"):
    return asyncio.run(gn.analyze_portfolio_impact(
        gn.PortfolioImpactRequest(country_code=country, headlines=headlines, tickers=tickers)
    ))


def test_identical_request_hits_the_cache(counted):
    first = _call(["a", "b", "c"])
    assert counted.n == 1

    second = _call(["a", "b", "c"])
    assert counted.n == 1, "a repeat click must not re-pay the LLM call"
    assert second == first


def test_different_headlines_is_a_different_question(counted):
    _call(["a", "b"])
    _call(["a", "c"])
    assert counted.n == 2


def test_different_country_is_a_different_question(counted):
    _call(["a"], country="US")
    _call(["a"], country="JP")
    assert counted.n == 2


def test_portfolio_is_part_of_the_cache_key(counted):
    """Same headlines against a different portfolio is a different answer —
    caching on headlines alone would serve one user's holdings to another."""
    _call(["a"], tickers=["TCS"])
    assert counted.n == 1
    _call(["a"], tickers=["INFY"])
    assert counted.n == 2, "the cache key must include the tickers"


def test_ticker_order_does_not_split_the_cache(counted):
    _call(["a"], tickers=["TCS", "INFY"])
    _call(["a"], tickers=["INFY", "TCS"])
    assert counted.n == 1, "the key sorts tickers — order is not a real difference"


def test_only_the_first_six_headlines_affect_the_key(counted):
    """The endpoint slices to 6, so headlines past that point can't change the
    answer and must not miss the cache."""
    _call(["a", "b", "c", "d", "e", "f", "SEVENTH"])
    _call(["a", "b", "c", "d", "e", "f", "DIFFERENT"])
    assert counted.n == 1


def test_failed_calls_are_not_cached(monkeypatch):
    """A fallback answer must not be pinned for 5 minutes — the next click
    should get a real retry."""
    calls = {"n": 0}

    def boom(*a, **kw):
        calls["n"] += 1
        raise RuntimeError("provider down")

    monkeypatch.setattr(gn.ai_client, "is_available", lambda: True)
    monkeypatch.setattr(gn.ai_client, "generate_grounded_json", boom)

    out = _call(["a"])
    assert out["affected_stocks"] == []
    _call(["a"])
    assert calls["n"] == 2, "a failure must not be cached"
