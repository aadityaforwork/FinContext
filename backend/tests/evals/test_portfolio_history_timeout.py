"""Portfolio risk history fetches must have a wall-clock ceiling."""

from __future__ import annotations

from app.services.portfolio import portfolio_analytics


def test_history_timeout_returns_empty_without_poisoning_cache(monkeypatch):
    symbol = "TIMEOUT.NS"
    period = "5y"
    cache_key = f"{symbol}_{period}"
    portfolio_analytics._history_cache.clear()

    def timeout(*args, **kwargs):
        assert kwargs["timeout_s"] == portfolio_analytics.HISTORY_FETCH_TIMEOUT_S
        return None, False

    monkeypatch.setattr(portfolio_analytics.yf_safe, "run_with_timeout", timeout)

    result = portfolio_analytics._fetch_close_series(symbol, period)

    assert result.empty
    assert cache_key not in portfolio_analytics._history_cache


def test_returned_empty_history_remains_cacheable(monkeypatch):
    symbol = "EMPTY.NS"
    period = "5y"
    cache_key = f"{symbol}_{period}"
    portfolio_analytics._history_cache.clear()

    monkeypatch.setattr(
        portfolio_analytics.yf_safe,
        "run_with_timeout",
        lambda *args, **kwargs: (portfolio_analytics.pd.Series(dtype=float), True),
    )

    result = portfolio_analytics._fetch_close_series(symbol, period)

    assert result.empty
    assert cache_key in portfolio_analytics._history_cache
