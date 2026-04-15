"""
Watchlist Router
================
CRUD endpoints for watchlist management with SQLite persistence.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
import yfinance as yf
from cachetools import TTLCache
from app.db import get_db
from app.db.models import WatchlistItem
from app.nse_universe import TICKER_TO_YF, TICKER_TO_META

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

# Price cache (2 min TTL)
_wl_price_cache = TTLCache(maxsize=100, ttl=120)


class AddToWatchlistRequest(BaseModel):
    ticker: str


class WatchlistItemResponse(BaseModel):
    ticker: str
    name: str
    sector: str
    current_price: float
    change_percent: float
    added_at: str


def _get_price(ticker: str) -> tuple[float, float]:
    """Get current price and change% for a ticker."""
    cache_key = f"wl_{ticker}"
    if cache_key in _wl_price_cache:
        return _wl_price_cache[cache_key]

    yf_symbol = TICKER_TO_YF.get(ticker)
    if not yf_symbol:
        return (0.0, 0.0)

    try:
        stock = yf.Ticker(yf_symbol)
        info = stock.fast_info
        price = float(info.last_price) if hasattr(info, 'last_price') else 0.0
        prev = float(info.previous_close) if hasattr(info, 'previous_close') else price
        change = ((price - prev) / prev * 100) if prev else 0.0
        result = (round(price, 2), round(change, 2))
        _wl_price_cache[cache_key] = result
        return result
    except Exception:
        return (0.0, 0.0)


@router.get("", response_model=list[WatchlistItemResponse])
@router.get("/", response_model=list[WatchlistItemResponse], include_in_schema=False)
async def get_watchlist(db: AsyncSession = Depends(get_db)):
    """Get all watchlisted stocks with live prices."""
    result = await db.execute(select(WatchlistItem))
    rows = result.scalars().all()

    items = []
    for row in rows:
        meta = TICKER_TO_META.get(row.ticker, {"name": row.ticker, "sector": "Unknown"})
        price, change = _get_price(row.ticker)
        items.append(WatchlistItemResponse(
            ticker=row.ticker,
            name=meta["name"],
            sector=meta["sector"],
            current_price=price,
            change_percent=change,
            added_at=row.added_at.isoformat() if row.added_at else "",
        ))
    return items


@router.post("/add")
async def add_to_watchlist(req: AddToWatchlistRequest, db: AsyncSession = Depends(get_db)):
    """Add a stock to the watchlist."""
    ticker = req.ticker.upper()
    if ticker not in TICKER_TO_YF:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found in NSE universe.")

    # Check if already exists
    result = await db.execute(select(WatchlistItem).where(WatchlistItem.ticker == ticker))
    if result.scalar_one_or_none():
        return {"message": f"{ticker} already in watchlist", "action": "exists"}

    db.add(WatchlistItem(ticker=ticker))
    return {"message": f"Added {ticker} to watchlist", "action": "added", "ticker": ticker}


@router.delete("/{ticker}")
async def remove_from_watchlist(ticker: str, db: AsyncSession = Depends(get_db)):
    """Remove a stock from the watchlist."""
    ticker = ticker.upper()
    result = await db.execute(select(WatchlistItem).where(WatchlistItem.ticker == ticker))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"{ticker} not in watchlist.")
    await db.execute(delete(WatchlistItem).where(WatchlistItem.ticker == ticker))
    return {"message": f"Removed {ticker} from watchlist", "ticker": ticker}
