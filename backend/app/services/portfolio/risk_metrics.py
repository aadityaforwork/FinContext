"""
Risk metrics — pure functions, no I/O.

Each function takes pre-computed pandas Series / DataFrames in and returns
plain floats / dicts out. No yfinance calls here, no caching, no LLM.

Why pure: lets us unit-test trivially with synthetic data, and lets the
orchestration layer (portfolio_analytics.py) decide which metrics to compute
without re-fetching prices.

Conventions:
- All "annualized" outputs assume 252 trading days/year.
- All "drawdown" outputs are negative fractions (e.g. -0.18 for a -18% peak-to-trough).
- All functions return None when there is not enough data — never raise.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

PERIODS_PER_YEAR = 252
DEFAULT_RISK_FREE_RATE = 0.06  # India 10y G-Sec ~6% — override per call when needed
MIN_OBSERVATIONS = 30          # sample-size floor below which we return None


# ---------------------------------------------------------------------------
# Returns
# ---------------------------------------------------------------------------
def daily_returns(prices: pd.Series) -> pd.Series:
    """Simple daily returns. Drops the first NaN."""
    if prices is None or prices.empty:
        return pd.Series(dtype=float)
    return prices.pct_change().dropna()


def cumulative_returns(returns: pd.Series) -> pd.Series:
    """Cumulative growth-of-1 series from a daily-returns series."""
    if returns is None or returns.empty:
        return pd.Series(dtype=float)
    return (1.0 + returns).cumprod()


# ---------------------------------------------------------------------------
# Single-asset / portfolio metrics
# ---------------------------------------------------------------------------
def annualized_volatility(returns: pd.Series, periods_per_year: int = PERIODS_PER_YEAR) -> float | None:
    if returns is None or len(returns) < MIN_OBSERVATIONS:
        return None
    sigma = float(returns.std())
    if math.isnan(sigma):
        return None
    return round(sigma * math.sqrt(periods_per_year), 4)


def beta(asset_returns: pd.Series, market_returns: pd.Series) -> float | None:
    """OLS-style beta = Cov(asset, market) / Var(market). Aligns dates first."""
    if asset_returns is None or market_returns is None:
        return None
    aligned = pd.concat([asset_returns, market_returns], axis=1, join="inner").dropna()
    if len(aligned) < MIN_OBSERVATIONS:
        return None
    a = aligned.iloc[:, 0]
    m = aligned.iloc[:, 1]
    var_m = float(m.var())
    if not var_m or math.isnan(var_m):
        return None
    cov = float(a.cov(m))
    if math.isnan(cov):
        return None
    return round(cov / var_m, 4)


def max_drawdown(prices_or_cum: pd.Series) -> float | None:
    """Worst peak-to-trough on a price (or cumulative-returns) series. Returns a negative fraction."""
    if prices_or_cum is None or len(prices_or_cum) < 2:
        return None
    series = prices_or_cum.dropna()
    if series.empty:
        return None
    rolling_max = series.cummax()
    dd = (series - rolling_max) / rolling_max
    worst = float(dd.min())
    if math.isnan(worst):
        return None
    return round(worst, 4)


def max_drawdown_window(returns: pd.Series, days: int) -> float | None:
    """Max drawdown over the trailing `days` of a daily-returns series."""
    if returns is None or returns.empty:
        return None
    tail = returns.tail(days)
    if len(tail) < MIN_OBSERVATIONS:
        return None
    cum = cumulative_returns(tail)
    return max_drawdown(cum)


def sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
    periods_per_year: int = PERIODS_PER_YEAR,
) -> float | None:
    """Annualised Sharpe = (mean_ret * 252 - rf) / (std * sqrt(252))."""
    if returns is None or len(returns) < MIN_OBSERVATIONS:
        return None
    mean = float(returns.mean())
    sigma = float(returns.std())
    if math.isnan(mean) or math.isnan(sigma) or sigma == 0:
        return None
    annualized_return = mean * periods_per_year
    annualized_vol = sigma * math.sqrt(periods_per_year)
    return round((annualized_return - risk_free_rate) / annualized_vol, 4)


# ---------------------------------------------------------------------------
# Concentration (§4.1, §4.7)
# ---------------------------------------------------------------------------
def sector_hhi(allocation_by_sector: dict[str, float]) -> float | None:
    """Herfindahl-Hirschman Index, normalized to [0, 1].

    1.0 = single-sector portfolio; 1/N = perfectly equal across N sectors.
    Treats input values as weights — they don't need to sum to 1.
    """
    if not allocation_by_sector:
        return None
    total = sum(float(v) for v in allocation_by_sector.values() if v)
    if total <= 0:
        return None
    shares = [float(v) / total for v in allocation_by_sector.values() if v]
    return round(sum(s * s for s in shares), 4)


# ---------------------------------------------------------------------------
# Correlation (§4.7)
# ---------------------------------------------------------------------------
def correlation_matrix(returns_df: pd.DataFrame) -> pd.DataFrame:
    """Pairwise daily-return correlations across columns."""
    if returns_df is None or returns_df.empty:
        return pd.DataFrame()
    return returns_df.corr()


def high_correlation_pairs(
    corr: pd.DataFrame,
    threshold: float = 0.75,
    limit: int = 20,
) -> list[dict]:
    """Pairs with correlation >= threshold, sorted descending."""
    if corr is None or corr.empty:
        return []
    cols = list(corr.columns)
    pairs: list[dict] = []
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            v = corr.iloc[i, j]
            if pd.notna(v) and float(v) >= threshold:
                pairs.append({
                    "a": cols[i],
                    "b": cols[j],
                    "correlation": round(float(v), 3),
                })
    pairs.sort(key=lambda p: -p["correlation"])
    return pairs[:limit]


# ---------------------------------------------------------------------------
# JSON-safety helpers — the matrix path produces NaN that JSON can't serialize.
# ---------------------------------------------------------------------------
def matrix_to_json_safe(corr: pd.DataFrame) -> list[list[float | None]]:
    """Convert a correlation DataFrame to nested lists with NaN -> None."""
    if corr is None or corr.empty:
        return []
    out: list[list[float | None]] = []
    for row in corr.values.tolist():
        out.append([None if (isinstance(v, float) and math.isnan(v)) else round(float(v), 4)
                    for v in row])
    return out
