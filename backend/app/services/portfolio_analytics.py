"""
Portfolio analytics — orchestrates price fetching and routes data to the pure
math functions in services.risk_metrics.

This is the only place that does I/O for portfolio-level risk: fetch 5y daily
closes for every holding plus NIFTY 50 in one parallel batch, build a returns
DataFrame, then call risk_metrics functions. Every metric reuses the SAME
returns DataFrame — no redundant fetches.

Public surface:
    compute_risk_brief(positions, *, risk_free_rate=0.06, history_period='5y') -> dict

Returns a dict that the router serves directly (after wrapping with the
disclaimer) and the risk-explainer agent narrates.
"""

from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Iterable

import pandas as pd
import yfinance as yf

from app.nse_universe import TICKER_TO_META
from app.services import market_data, risk_metrics
from app.services.cache import make_cache

logger = logging.getLogger(__name__)

# Price-history cache for risk fetches. Tuned larger than market_data's history
# cache because we hit ~10–25 tickers per request and want hits across users.
_history_cache = make_cache(maxsize=300, ttl_seconds=1800)  # 30 min

NIFTY_KEY = "__NIFTY50__"
NIFTY_SYMBOL = "^NSEI"

DRAWDOWN_WINDOWS = {
    "1y": 252,
    "3y": 756,
    "5y": 1260,
}


# ---------------------------------------------------------------------------
# Internal: price fetch
# ---------------------------------------------------------------------------
def _fetch_close_series(yf_symbol: str, period: str) -> pd.Series:
    """Fetch a close-price Series from yfinance. Empty Series on failure."""
    cache_key = f"{yf_symbol}_{period}"
    if cache_key in _history_cache:
        return _history_cache[cache_key]
    try:
        hist = yf.Ticker(yf_symbol).history(period=period)
        if hist is None or hist.empty:
            empty = pd.Series(dtype=float)
            _history_cache[cache_key] = empty
            return empty
        # Drop tz to keep arithmetic & alignment simple across symbols.
        if hist.index.tz is not None:
            hist.index = hist.index.tz_localize(None)
        s = hist["Close"].astype(float)
        _history_cache[cache_key] = s
        return s
    except Exception as e:
        logger.warning("price-history fetch failed for %s: %s", yf_symbol, e)
        return pd.Series(dtype=float)


def _parallel_fetch(symbols: dict[str, str], period: str) -> dict[str, pd.Series]:
    """Fetch all close-series in parallel. `symbols` is {ticker_label: yf_symbol}.

    Returns only labels whose fetch succeeded with a non-empty series.
    """
    out: dict[str, pd.Series] = {}
    if not symbols:
        return out
    with ThreadPoolExecutor(max_workers=min(16, len(symbols))) as ex:
        future_to_label = {
            ex.submit(_fetch_close_series, sym, period): label
            for label, sym in symbols.items()
        }
        for fut in as_completed(future_to_label):
            label = future_to_label[fut]
            try:
                s = fut.result()
                if s is not None and not s.empty:
                    out[label] = s
            except Exception as e:
                logger.warning("fetch task for %s failed: %s", label, e)
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def compute_risk_brief(
    positions: Iterable[dict],
    *,
    risk_free_rate: float = risk_metrics.DEFAULT_RISK_FREE_RATE,
    history_period: str = "5y",
) -> dict:
    """Compute the full risk + concentration report for a list of positions.

    `positions`: iterable of {"ticker": str, "quantity": float, "buy_price": float}.

    Output (all numeric fields may be None if data is insufficient):
        {
          "metrics": { volatility_annualized, beta_vs_nifty50, max_drawdown_1y/3y/5y,
                       sharpe_ratio, risk_free_rate_used, sample_size_days },
          "concentration": { sector_hhi, top_holding_pct, top_3_holdings_pct,
                             top_sector_pct, flagged_clusters },
          "correlations": { tickers, matrix, high_correlation_pairs },
          "holdings_value": { ticker -> current_value },
          "data_gaps": [ str, ... ],
        }
    """
    positions = list(positions)
    data_gaps: list[str] = []
    empty_report = _empty_report(risk_free_rate)

    if not positions:
        return {**empty_report, "data_gaps": ["no positions provided"]}

    # 1. Resolve yfinance symbols. Skip unknowns with a data_gap.
    by_ticker = {p["ticker"].upper(): p for p in positions if p.get("ticker")}
    yf_symbols: dict[str, str] = {}
    for t in by_ticker:
        sym = market_data.resolve_yf_symbol(t)
        if sym:
            yf_symbols[t] = sym
        else:
            data_gaps.append(f"{t}: ticker not in NSE universe; excluded from risk math")

    if not yf_symbols:
        return {**empty_report, "data_gaps": data_gaps or ["no resolvable tickers"]}

    # 2. Parallel fetch: holdings + NIFTY 50 in one batch.
    fetch_targets = dict(yf_symbols)
    fetch_targets[NIFTY_KEY] = NIFTY_SYMBOL
    series_by_label = _parallel_fetch(fetch_targets, history_period)

    nifty_close = series_by_label.pop(NIFTY_KEY, pd.Series(dtype=float))
    nifty_returns = risk_metrics.daily_returns(nifty_close) if not nifty_close.empty else pd.Series(dtype=float)
    if nifty_returns.empty:
        data_gaps.append("NIFTY 50 history unavailable; beta cannot be computed")

    # 3. Drop holdings with too-short history; surface them as gaps.
    usable: dict[str, pd.Series] = {}
    for t, s in series_by_label.items():
        if len(s) < risk_metrics.MIN_OBSERVATIONS + 1:  # +1 because pct_change drops one
            data_gaps.append(f"{t}: insufficient price history ({len(s)} days); excluded")
            continue
        usable[t] = s

    if not usable:
        return {**empty_report, "data_gaps": data_gaps}

    # 4. Returns DataFrame, aligned on outer-join then filled with NaN intentionally.
    returns_df = pd.DataFrame({t: risk_metrics.daily_returns(s) for t, s in usable.items()})

    # 5. Weights by current value (latest close × qty). Position with no fetched
    #    price — or a NaN last close (happens for partially-delisted tickers
    #    like INTEGRAEN where yfinance returns NaN) — falls back to buy_price so
    #    a single bad price can't poison total_value into NaN.
    current_values: dict[str, float] = {}
    for t, s in usable.items():
        pos = by_ticker.get(t)
        if not pos:
            continue
        buy_price = float(pos.get("buy_price") or 0)
        latest = float(s.iloc[-1]) if not s.empty else buy_price
        if math.isnan(latest) or latest <= 0:
            latest = buy_price
            data_gaps.append(f"{t}: latest close unavailable; valued at buy price")
        qty = float(pos.get("quantity") or 0)
        val = latest * qty
        current_values[t] = val if not math.isnan(val) else 0.0
    total_value = sum(current_values.values())
    # `NaN <= 0` is False — so guard isnan explicitly or NaN slips straight
    # through into the concentration math below.
    if math.isnan(total_value) or total_value <= 0:
        return {**empty_report, "data_gaps": data_gaps + ["zero portfolio value"]}
    weights = pd.Series({t: v / total_value for t, v in current_values.items()})

    # 6. Portfolio daily returns: weighted sum across columns. NaN-fill 0 so a
    #    short-history holding doesn't void the whole day for the portfolio.
    aligned_returns = returns_df[weights.index].fillna(0.0)
    portfolio_returns = (aligned_returns.mul(weights, axis=1)).sum(axis=1).dropna()

    # 7. Metrics.
    vol = risk_metrics.annualized_volatility(portfolio_returns)
    sharpe = risk_metrics.sharpe_ratio(portfolio_returns, risk_free_rate=risk_free_rate)
    beta_val = risk_metrics.beta(portfolio_returns, nifty_returns) if not nifty_returns.empty else None

    drawdowns = {
        f"max_drawdown_{label}": risk_metrics.max_drawdown_window(portfolio_returns, days)
        for label, days in DRAWDOWN_WINDOWS.items()
    }

    # 8. Concentration.
    sector_alloc: dict[str, float] = {}
    for t, v in current_values.items():
        sector = (TICKER_TO_META.get(t) or {}).get("sector") or "Unknown"
        sector_alloc[sector] = sector_alloc.get(sector, 0.0) + v
    hhi = risk_metrics.sector_hhi(sector_alloc)
    sorted_holdings = sorted(current_values.items(), key=lambda x: -x[1])
    top1 = sorted_holdings[0][1] / total_value * 100 if sorted_holdings else None
    top3 = sum(v for _, v in sorted_holdings[:3]) / total_value * 100 if sorted_holdings else None
    top_sector_pct = (max(sector_alloc.values()) / total_value * 100) if sector_alloc else None

    # 9. Correlations and flagged clusters.
    corr = risk_metrics.correlation_matrix(returns_df.dropna(how="all"))
    pairs = risk_metrics.high_correlation_pairs(corr, threshold=0.75, limit=20)
    flagged_clusters = [
        f"{p['a']} ↔ {p['b']}: {p['correlation']:.2f} correlation (≥ 0.75)"
        for p in pairs[:5]
    ]

    report = {
        "metrics": {
            "volatility_annualized": vol,
            "beta_vs_nifty50": beta_val,
            **{k: round(v, 4) if isinstance(v, float) else v for k, v in drawdowns.items()},
            "sharpe_ratio": sharpe,
            "risk_free_rate_used": risk_free_rate,
            "sample_size_days": int(len(portfolio_returns)),
        },
        "concentration": {
            "sector_hhi": hhi,
            "top_holding_pct": round(top1, 2) if top1 is not None else None,
            "top_3_holdings_pct": round(top3, 2) if top3 is not None else None,
            "top_sector_pct": round(top_sector_pct, 2) if top_sector_pct is not None else None,
            "sector_allocation_pct": [
                {"sector": k, "value": round(v, 2), "percent": round(v / total_value * 100, 2)}
                for k, v in sorted(sector_alloc.items(), key=lambda x: -x[1])
            ],
            "flagged_clusters": flagged_clusters,
        },
        "correlations": {
            "tickers": list(corr.columns) if not corr.empty else [],
            "matrix": risk_metrics.matrix_to_json_safe(corr),
            "high_correlation_pairs": pairs[:10],
        },
        "holdings_value": {t: round(v, 2) for t, v in current_values.items()},
        "data_gaps": data_gaps,
    }
    # Belt-and-suspenders: even with the source guards above, recursively scrub
    # any NaN / Inf that slipped through — those are not JSON-serializable and
    # crash the FastAPI response with "Out of range float values".
    return _json_safe(report)


def _json_safe(obj: Any) -> Any:
    """Recursively replace NaN / Inf floats with None so the payload is always
    JSON-serializable. Walks dicts, lists, tuples; leaves everything else alone.
    """
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def _empty_report(risk_free_rate: float) -> dict:
    return {
        "metrics": {
            "volatility_annualized": None,
            "beta_vs_nifty50": None,
            "max_drawdown_1y": None,
            "max_drawdown_3y": None,
            "max_drawdown_5y": None,
            "sharpe_ratio": None,
            "risk_free_rate_used": risk_free_rate,
            "sample_size_days": 0,
        },
        "concentration": {
            "sector_hhi": None,
            "top_holding_pct": None,
            "top_3_holdings_pct": None,
            "top_sector_pct": None,
            "sector_allocation_pct": [],
            "flagged_clusters": [],
        },
        "correlations": {"tickers": [], "matrix": [], "high_correlation_pairs": []},
        "holdings_value": {},
    }
