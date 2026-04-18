"""
Portfolio P&L enrichment endpoint.
Accepts positions array from the frontend (stored in Supabase),
fetches live prices, computes P&L, and returns a full summary.
No auth required — scoping is done on the frontend via Supabase.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter
from pydantic import BaseModel
from cachetools import TTLCache
import yfinance as yf
from app.nse_universe import TICKER_TO_YF, TICKER_TO_META

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

_price_cache = TTLCache(maxsize=500, ttl=180)
_price_executor = ThreadPoolExecutor(max_workers=16)


class PositionIn(BaseModel):
    ticker: str
    quantity: float
    buy_price: float


class EnrichRequest(BaseModel):
    positions: list[PositionIn]


def _get_live_price(ticker: str) -> tuple[float, float]:
    if ticker in _price_cache:
        return _price_cache[ticker]
    yf_symbol = TICKER_TO_YF.get(ticker)
    if not yf_symbol:
        return (0.0, 0.0)
    try:
        info = yf.Ticker(yf_symbol).fast_info
        price = float(info.last_price) if hasattr(info, "last_price") else 0.0
        prev = float(info.previous_close) if hasattr(info, "previous_close") else price
        change_pct = ((price - prev) / prev * 100) if prev else 0.0
        result = (round(price, 2), round(change_pct, 2))
        _price_cache[ticker] = result
        return result
    except Exception:
        return (0.0, 0.0)


@router.post("/enrich")
async def enrich_portfolio(req: EnrichRequest):
    """Enrich positions with live prices and return a full P&L summary."""
    positions = []
    total_invested = 0.0
    current_value = 0.0
    day_change = 0.0

    tickers = [p.ticker.upper() for p in req.positions]
    loop = asyncio.get_running_loop()
    quotes = await asyncio.gather(*[
        loop.run_in_executor(_price_executor, _get_live_price, t) for t in tickers
    ]) if tickers else []
    quote_map = dict(zip(tickers, quotes))

    for pos in req.positions:
        ticker = pos.ticker.upper()
        meta = TICKER_TO_META.get(ticker, {"name": ticker, "sector": "Unknown"})
        price, change_pct = quote_map.get(ticker, (0.0, 0.0))
        if price == 0:
            price = pos.buy_price

        invested = pos.quantity * pos.buy_price
        current = pos.quantity * price
        pnl = current - invested
        pnl_pct = (pnl / invested * 100) if invested else 0.0

        total_invested += invested
        current_value += current
        day_change += current * (change_pct / 100)

        positions.append({
            "ticker": ticker,
            "name": meta["name"],
            "sector": meta["sector"],
            "quantity": pos.quantity,
            "buy_price": pos.buy_price,
            "current_price": price,
            "invested_value": round(invested, 2),
            "current_value": round(current, 2),
            "pnl": round(pnl, 2),
            "pnl_percent": round(pnl_pct, 2),
        })

    total_pnl = current_value - total_invested
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested else 0.0
    day_change_pct = (day_change / current_value * 100) if current_value else 0.0

    allocation: dict[str, float] = {}
    for p in positions:
        allocation[p["sector"]] = allocation.get(p["sector"], 0) + p["current_value"]
    allocation_list = [
        {"sector": k, "value": round(v, 2), "percent": round(v / current_value * 100, 1) if current_value else 0}
        for k, v in sorted(allocation.items(), key=lambda x: -x[1])
    ]

    return {
        "total_invested": round(total_invested, 2),
        "current_value": round(current_value, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_percent": round(total_pnl_pct, 2),
        "day_change": round(day_change, 2),
        "day_change_percent": round(day_change_pct, 2),
        "holdings_count": len(positions),
        "positions": positions,
        "allocation": allocation_list,
    }
