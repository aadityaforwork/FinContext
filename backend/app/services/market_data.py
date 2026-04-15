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
# Caching: avoid hammering Yahoo Finance
# ---------------------------------------------------------------------------
# price cache: 5 min TTL, max 50 entries
_price_cache = TTLCache(maxsize=50, ttl=300)
# history cache: 10 min TTL, max 20 entries
_history_cache = TTLCache(maxsize=20, ttl=600)
# index cache: 3 min TTL
_index_cache = TTLCache(maxsize=10, ttl=180)


def get_live_quote(ticker: str) -> dict | None:
    """
    Get the current/latest quote for a stock ticker.
    Returns dict with: current_price, change_percent, market_cap_cr, day_high, day_low, volume
    Falls back to seed data if yfinance fails.
    """
    cache_key = f"quote_{ticker}"
    if cache_key in _price_cache:
        return _price_cache[cache_key]

    yf_symbol = TICKER_MAP.get(ticker)
    if not yf_symbol:
        return None

    try:
        stock = yf.Ticker(yf_symbol)
        info = stock.fast_info

        current_price = float(info.last_price) if hasattr(info, 'last_price') else float(info.get("lastPrice", 0))
        prev_close = float(info.previous_close) if hasattr(info, 'previous_close') else float(info.get("previousClose", 0))
        change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close else 0
        market_cap = float(info.market_cap) / 1e7 if hasattr(info, 'market_cap') and info.market_cap else None  # Convert to Cr

        result = {
            "current_price": round(current_price, 2),
            "change_percent": round(change_pct, 2),
            "market_cap_cr": round(market_cap, 0) if market_cap else None,
        }
        _price_cache[cache_key] = result
        return result
    except Exception as e:
        logger.warning(f"yfinance quote failed for {ticker} ({yf_symbol}): {e}")
        return None


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

    yf_symbol = TICKER_MAP.get(ticker)
    if not yf_symbol:
        return []

    try:
        stock = yf.Ticker(yf_symbol)
        hist = stock.history(period=period)

        if hist.empty:
            logger.warning(f"No history data for {ticker} ({yf_symbol})")
            return []

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

        _history_cache[cache_key] = data
        return data
    except Exception as e:
        logger.warning(f"yfinance history failed for {ticker} ({yf_symbol}): {e}")
        return []


def get_market_indices() -> list[dict]:
    """
    Get live market index values for the dashboard overview.
    Returns list of {label, value, change, positive} dicts.
    """
    cache_key = "market_indices"
    if cache_key in _index_cache:
        return _index_cache[cache_key]

    results = []
    for label, symbol in INDEX_MAP.items():
        try:
            tk = yf.Ticker(symbol)

            price = 0.0
            prev = 0.0

            # Try fast_info first
            try:
                info = tk.fast_info
                if info is not None:
                    price = float(getattr(info, 'last_price', 0) or 0)
                    prev = float(getattr(info, 'previous_close', 0) or 0)
            except Exception:
                pass

            # Fallback: use recent history if fast_info didn't work
            if price == 0.0:
                try:
                    hist = tk.history(period="5d")
                    if not hist.empty and len(hist) >= 1:
                        price = float(hist["Close"].iloc[-1])
                        prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else price
                except Exception:
                    pass

            if price == 0.0:
                raise ValueError("Could not fetch price data")

            change_pct = ((price - prev) / prev * 100) if prev else 0

            # Format the value
            if label == "INR/USD":
                value = f"{price:.2f}"
            else:
                value = f"{price:,.2f}"

            results.append({
                "label": label,
                "value": value,
                "change": f"{'+'if change_pct >= 0 else ''}{change_pct:.2f}%",
                "positive": change_pct >= 0,
            })
        except Exception as e:
            logger.warning(f"Index fetch failed for {label} ({symbol}): {e}")
            results.append({
                "label": label,
                "value": "—",
                "change": "—",
                "positive": True,
            })

    _index_cache[cache_key] = results
    return results
