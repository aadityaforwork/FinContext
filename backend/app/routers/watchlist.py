"""
Watchlist price-enrichment endpoint.
Accepts a list of tickers, returns live prices from yfinance.
No auth required — data scoping is handled by Supabase RLS on the frontend.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter
from pydantic import BaseModel
from cachetools import TTLCache
import yfinance as yf
from app.nse_universe import TICKER_TO_YF, TICKER_TO_META, resolve_yf_symbol
from app.services import yf_safe

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

_price_cache: TTLCache = TTLCache(maxsize=300, ttl=180)
_price_neg_perm: TTLCache = TTLCache(maxsize=500, ttl=yf_safe.NEG_TTL_PERMANENT_S)
_price_neg_transient: TTLCache = TTLCache(maxsize=300, ttl=yf_safe.NEG_TTL_TRANSIENT_S)
_price_executor = ThreadPoolExecutor(max_workers=12)


class PriceRequest(BaseModel):
    tickers: list[str]


def _fetch_inner(yf_symbol: str) -> tuple[float | None, float | None] | None:
    """Pure yfinance call. Does NOT catch exceptions — see the matching note
    in routers/portfolio.py._fetch_price_inner. Swallowing the exception here
    poisons real tickers as permanent (24h) on transient rate limits."""
    info = yf.Ticker(yf_symbol).fast_info
    price = float(info.last_price) if hasattr(info, "last_price") else None
    prev = float(info.previous_close) if hasattr(info, "previous_close") else None
    if price is None or prev is None or prev == 0:
        return None
    return (round(price, 2), round((price - prev) / prev * 100, 2))


def _get_price(ticker: str) -> tuple[float | None, float | None]:
    """Returns (price, change_percent). None means we couldn't get live data
    (unknown ticker or fetch failure) — UI renders "—" instead of misleading "+0.0%".

    Hardened with yf_safe — 5s wall timeout, 24h cache for delisted symbols.
    """
    if ticker in _price_cache:
        return _price_cache[ticker]
    if ticker in _price_neg_perm or ticker in _price_neg_transient:
        return (None, None)
    yf_symbol = resolve_yf_symbol(ticker)
    if not yf_symbol:
        _price_neg_perm[ticker] = True
        return (None, None)

    result, ok = yf_safe.run_with_timeout(_fetch_inner, yf_symbol, timeout_s=5.0)
    if not ok:
        exc = result if isinstance(result, Exception) else None
        kind = yf_safe.classify_error(exc, None if exc is None else "__sentinel__")
        if kind == "permanent":
            _price_neg_perm[ticker] = True
        else:
            _price_neg_transient[ticker] = True
        return (None, None)
    if result is None:
        _price_neg_perm[ticker] = True
        return (None, None)
    _price_cache[ticker] = result
    return result


@router.post("/prices")
async def get_prices(req: PriceRequest):
    """Return a map of ticker → {name, sector, current_price, change_percent}."""
    tickers = [t.upper() for t in req.tickers]
    if not tickers:
        return {}

    loop = asyncio.get_running_loop()
    quotes = await asyncio.gather(*[
        loop.run_in_executor(_price_executor, _get_price, t) for t in tickers
    ])

    result = {}
    for ticker, (price, change) in zip(tickers, quotes):
        meta = TICKER_TO_META.get(ticker, {"name": ticker, "sector": "Unknown"})
        result[ticker] = {
            "name": meta["name"],
            "sector": meta["sector"],
            "current_price": price,
            "change_percent": change,
        }
    return result
