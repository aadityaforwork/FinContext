"""
Market Data Service
====================
Real-time stock prices and market indices via yfinance.

Provides:
- Live/delayed stock quotes for NSE-listed equities
- Historical OHLCV data for charting
- Market index values (NIFTY 50, SENSEX, etc.)
- In-memory caching to avoid rate limiting
"""

import yfinance as yf
from cachetools import TTLCache
from datetime import datetime
import logging

from app.nse_universe import TICKER_TO_YF
from app.services import yf_safe

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Ticker Mapping: Internal ticker → NSE Yahoo Finance symbol
# ---------------------------------------------------------------------------
TICKER_MAP = {
    "REC": "RECLTD.NS",
    "RVNL": "RVNL.NS",
    "HBLENGR": "HBLPOWER.NS",
    "TATAMOTORS-TMCV": "TATAMOTORS.NS",
    "TATAMOTORS-TMPV": "TATAMOTORS.NS",
}

# Stock metadata (sector info isn't always available from yfinance)
STOCK_META = {
    "REC": {"name": "REC Limited", "sector": "Power & Infrastructure Finance"},
    "RVNL": {"name": "Rail Vikas Nigam Ltd", "sector": "Infrastructure - Railways"},
    "HBLENGR": {"name": "HBL Engineering Ltd", "sector": "Capital Goods - Electronics"},
    "TATAMOTORS-TMCV": {"name": "Tata Motors - Commercial Vehicles", "sector": "Automobiles - CV"},
    "TATAMOTORS-TMPV": {"name": "Tata Motors - Passenger Vehicles", "sector": "Automobiles - PV & EV"},
}

# Index symbols for market overview
INDEX_MAP = {
    "NIFTY 50": "^NSEI",
    "SENSEX": "^BSESN",
    "NIFTY MIDCAP": "NIFTY_MIDCAP_100.NS",
    "INR/USD": "INR=X",
}

# ---------------------------------------------------------------------------
# Symbol resolution — TICKER_MAP holds custom overrides (e.g. for split tickers
# like TATAMOTORS-TMCV); TICKER_TO_YF holds the full NSE universe (~150 names).
# Always check the override first so custom mappings win.
# ---------------------------------------------------------------------------
def resolve_yf_symbol(ticker: str) -> str | None:
    """Resolve an internal ticker to its yfinance symbol, or None if unknown."""
    if not ticker:
        return None
    return TICKER_MAP.get(ticker) or TICKER_TO_YF.get(ticker.upper())


# ---------------------------------------------------------------------------
# Caching: avoid hammering Yahoo Finance
# ---------------------------------------------------------------------------
# price cache: 5 min TTL, max 50 entries
_price_cache = TTLCache(maxsize=50, ttl=300)
_price_neg_perm: TTLCache = TTLCache(maxsize=200, ttl=yf_safe.NEG_TTL_PERMANENT_S)
_price_neg_transient: TTLCache = TTLCache(maxsize=100, ttl=yf_safe.NEG_TTL_TRANSIENT_S)
# history cache: 10 min TTL, max 20 entries
_history_cache = TTLCache(maxsize=20, ttl=600)
_history_neg_perm: TTLCache = TTLCache(maxsize=200, ttl=yf_safe.NEG_TTL_PERMANENT_S)
_history_neg_transient: TTLCache = TTLCache(maxsize=100, ttl=yf_safe.NEG_TTL_TRANSIENT_S)
# index cache: 3 min TTL
_index_cache = TTLCache(maxsize=10, ttl=180)
_index_neg_perm: TTLCache = TTLCache(maxsize=20, ttl=yf_safe.NEG_TTL_PERMANENT_S)
_index_neg_transient: TTLCache = TTLCache(maxsize=20, ttl=yf_safe.NEG_TTL_TRANSIENT_S)


def get_live_quote(ticker: str) -> dict | None:
    """
    Get the current/latest quote for a stock ticker.
    Returns dict with: current_price, change_percent, market_cap_cr, day_high, day_low, volume
    Falls back to seed data if yfinance fails.

    Hardened with yf_safe — 5s wall timeout, 24h cache for delisted symbols.
    """
    cache_key = f"quote_{ticker}"
    if cache_key in _price_cache:
        return _price_cache[cache_key]
    if cache_key in _price_neg_perm or cache_key in _price_neg_transient:
        return None

    yf_symbol = resolve_yf_symbol(ticker)
    if not yf_symbol:
        _price_neg_perm[cache_key] = True
        return None

    def _inner() -> dict | None:
        try:
            stock = yf.Ticker(yf_symbol)
            info = stock.fast_info
            current_price = float(info.last_price) if hasattr(info, 'last_price') else float(info.get("lastPrice", 0))
            prev_close = float(info.previous_close) if hasattr(info, 'previous_close') else float(info.get("previousClose", 0))
            market_cap = float(info.market_cap) / 1e7 if hasattr(info, 'market_cap') and info.market_cap else None
        except Exception:
            return None
        if not current_price or not prev_close:
            return None
        change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close else 0
        return {
            "current_price": round(current_price, 2),
            "change_percent": round(change_pct, 2),
            "market_cap_cr": round(market_cap, 0) if market_cap else None,
        }

    result, ok = yf_safe.run_with_timeout(_inner, timeout_s=5.0)
    if not ok:
        exc = result if isinstance(result, Exception) else None
        kind = yf_safe.classify_error(exc, None if exc is None else "__sentinel__")
        if kind == "permanent":
            _price_neg_perm[cache_key] = True
        else:
            _price_neg_transient[cache_key] = True
        if exc is not None:
            logger.warning(f"yfinance quote failed for {ticker} ({yf_symbol}): {exc}")
        return None
    if result is None:
        _price_neg_perm[cache_key] = True
        return None
    _price_cache[cache_key] = result
    return result


def get_price_history(ticker: str, period: str = "1mo") -> list[dict]:
    """
    Get historical OHLCV data for charting.
    
    Args:
        ticker: Internal ticker symbol
        period: yfinance period string (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, max)
    
    Returns:
        List of {date, open, high, low, close, volume} dicts
    """
    cache_key = f"history_{ticker}_{period}"
    if cache_key in _history_cache:
        return _history_cache[cache_key]
    if cache_key in _history_neg_perm or cache_key in _history_neg_transient:
        return []

    yf_symbol = resolve_yf_symbol(ticker)
    if not yf_symbol:
        _history_neg_perm[cache_key] = True
        return []

    def _inner() -> list[dict] | None:
        stock = yf.Ticker(yf_symbol)
        hist = stock.history(period=period)
        if hist is None or hist.empty:
            return None
        data = []
        for idx, row in hist.iterrows():
            data.append({
                "date": idx.strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            })
        return data

    # 8s budget — history is heavier than fast_info (downloads bars).
    result, ok = yf_safe.run_with_timeout(_inner, timeout_s=8.0)
    if not ok:
        exc = result if isinstance(result, Exception) else None
        kind = yf_safe.classify_error(exc, None if exc is None else "__sentinel__")
        if kind == "permanent":
            _history_neg_perm[cache_key] = True
        else:
            _history_neg_transient[cache_key] = True
        if exc is not None:
            logger.warning(f"yfinance history failed for {ticker} ({yf_symbol}): {exc}")
        return []
    if result is None:
        _history_neg_perm[cache_key] = True
        return []
    _history_cache[cache_key] = result
    return result


def get_market_indices() -> list[dict]:
    """
    Get live market index values for the dashboard overview.
    Returns list of {label, value, change, positive} dicts.
    """
    cache_key = "market_indices"
    if cache_key in _index_cache:
        return _index_cache[cache_key]

    def _fetch_one_index(symbol: str) -> tuple[float, float] | None:
        tk = yf.Ticker(symbol)
        price = prev = 0.0
        try:
            info = tk.fast_info
            if info is not None:
                price = float(getattr(info, 'last_price', 0) or 0)
                prev = float(getattr(info, 'previous_close', 0) or 0)
        except Exception:
            pass
        if price == 0.0:
            try:
                hist = tk.history(period="5d")
                if hist is not None and not hist.empty:
                    price = float(hist["Close"].iloc[-1])
                    prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else price
            except Exception:
                pass
        if price == 0.0:
            return None
        return (price, prev)

    results = []
    for label, symbol in INDEX_MAP.items():
        cache_key = f"idx_{symbol}"
        if cache_key in _index_neg_perm or cache_key in _index_neg_transient:
            results.append({"label": label, "value": "—", "change": "—", "positive": True})
            continue
        out, ok = yf_safe.run_with_timeout(_fetch_one_index, symbol, timeout_s=5.0)
        if not ok or out is None:
            exc = out if isinstance(out, Exception) else None
            kind = yf_safe.classify_error(exc, None if exc is None else "__sentinel__")
            if kind == "permanent":
                _index_neg_perm[cache_key] = True
            else:
                _index_neg_transient[cache_key] = True
            if exc is not None:
                logger.warning(f"Index fetch failed for {label} ({symbol}): {exc}")
            results.append({"label": label, "value": "—", "change": "—", "positive": True})
            continue

        price, prev = out
        change_pct = ((price - prev) / prev * 100) if prev else 0
        value = f"{price:.2f}" if label == "INR/USD" else f"{price:,.2f}"
        results.append({
            "label": label,
            "value": value,
            "change": f"{'+'if change_pct >= 0 else ''}{change_pct:.2f}%",
            "positive": change_pct >= 0,
        })

    _index_cache[cache_key] = results
    return results
