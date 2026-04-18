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
from app.nse_universe import TICKER_TO_YF, TICKER_TO_META

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

_price_cache = TTLCache(maxsize=500, ttl=180)
_price_executor = ThreadPoolExecutor(max_workers=16)


class PriceRequest(BaseModel):
    tickers: list[str]


def _get_price(ticker: str) -> tuple[float, float]:
    if ticker in _price_cache:
        return _price_cache[ticker]
    yf_symbol = TICKER_TO_YF.get(ticker)
    if not yf_symbol:
        return (0.0, 0.0)
    try:
        info = yf.Ticker(yf_symbol).fast_info
        price = float(info.last_price) if hasattr(info, "last_price") else 0.0
        prev = float(info.previous_close) if hasattr(info, "previous_close") else price
        change = ((price - prev) / prev * 100) if prev else 0.0
        result = (round(price, 2), round(change, 2))
        _price_cache[ticker] = result
        return result
    except Exception:
        return (0.0, 0.0)


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
