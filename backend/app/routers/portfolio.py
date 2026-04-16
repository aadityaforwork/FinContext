"""
Portfolio Router
================
CRUD endpoints for portfolio management with SQLite persistence.
Each user has their own portfolio.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
import yfinance as yf
from cachetools import TTLCache
from app.db import get_db
from app.db.models import PortfolioPosition, User
from app.core.deps import get_current_user
from app.nse_universe import TICKER_TO_YF, TICKER_TO_META

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

# Price cache for portfolio view (2 min TTL)
_portfolio_price_cache = TTLCache(maxsize=200, ttl=120)


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------
class AddPositionRequest(BaseModel):
    ticker: str
    quantity: float
    buy_price: float


class PositionResponse(BaseModel):
    ticker: str
    name: str
    sector: str
    quantity: float
    buy_price: float
    current_price: float
    invested_value: float
    current_value: float
    pnl: float
    pnl_percent: float
    added_at: str


class PortfolioSummary(BaseModel):
    total_invested: float
    current_value: float
    total_pnl: float
    total_pnl_percent: float
    day_change: float
    day_change_percent: float
    holdings_count: int
    positions: list[PositionResponse]
    allocation: list[dict]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_live_price(ticker: str) -> tuple[float, float]:
    """Get current price and change% for a ticker. Returns (price, change_pct)."""
    cache_key = f"pf_{ticker}"
    if cache_key in _portfolio_price_cache:
        return _portfolio_price_cache[cache_key]

    yf_symbol = TICKER_TO_YF.get(ticker)
    if not yf_symbol:
        return (0.0, 0.0)

    try:
        stock = yf.Ticker(yf_symbol)
        info = stock.fast_info
        price = float(info.last_price) if hasattr(info, 'last_price') else 0.0
        prev = float(info.previous_close) if hasattr(info, 'previous_close') else price
        change_pct = ((price - prev) / prev * 100) if prev else 0.0
        result = (round(price, 2), round(change_pct, 2))
        _portfolio_price_cache[cache_key] = result
        return result
    except Exception:
        return (0.0, 0.0)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/", response_model=PortfolioSummary)
async def get_portfolio(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all portfolio positions with live P&L calculation."""
    result = await db.execute(
        select(PortfolioPosition).where(PortfolioPosition.user_id == current_user.id)
    )
    rows = result.scalars().all()

    positions = []
    total_invested = 0.0
    current_value = 0.0
    day_change = 0.0

    for pos in rows:
        meta = TICKER_TO_META.get(pos.ticker, {"name": pos.ticker, "sector": "Unknown"})
        price, change_pct = _get_live_price(pos.ticker)

        if price == 0:
            price = pos.buy_price  # fallback

        invested = pos.quantity * pos.buy_price
        current = pos.quantity * price
        pnl = current - invested
        pnl_pct = (pnl / invested * 100) if invested else 0

        total_invested += invested
        current_value += current
        day_change += current * (change_pct / 100)

        positions.append(PositionResponse(
            ticker=pos.ticker,
            name=meta["name"],
            sector=meta["sector"],
            quantity=pos.quantity,
            buy_price=pos.buy_price,
            current_price=price,
            invested_value=round(invested, 2),
            current_value=round(current, 2),
            pnl=round(pnl, 2),
            pnl_percent=round(pnl_pct, 2),
            added_at=pos.added_at.isoformat() if pos.added_at else "",
        ))

    total_pnl = current_value - total_invested
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested else 0
    day_change_pct = (day_change / current_value * 100) if current_value else 0

    # Allocation breakdown by sector
    allocation = {}
    for p in positions:
        allocation[p.sector] = allocation.get(p.sector, 0) + p.current_value
    allocation_list = [
        {"sector": k, "value": round(v, 2), "percent": round(v / current_value * 100, 1) if current_value else 0}
        for k, v in sorted(allocation.items(), key=lambda x: -x[1])
    ]

    return PortfolioSummary(
        total_invested=round(total_invested, 2),
        current_value=round(current_value, 2),
        total_pnl=round(total_pnl, 2),
        total_pnl_percent=round(total_pnl_pct, 2),
        day_change=round(day_change, 2),
        day_change_percent=round(day_change_pct, 2),
        holdings_count=len(positions),
        positions=positions,
        allocation=allocation_list,
    )


@router.post("/add")
async def add_position(
    req: AddPositionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a stock position to the portfolio (averages if already exists)."""
    ticker = req.ticker.upper()

    if ticker not in TICKER_TO_YF:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found in NSE universe.")

    # Check if position exists for this user
    result = await db.execute(
        select(PortfolioPosition).where(
            PortfolioPosition.user_id == current_user.id,
            PortfolioPosition.ticker == ticker,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        # Average up/down
        total_qty = existing.quantity + req.quantity
        avg_price = (existing.quantity * existing.buy_price + req.quantity * req.buy_price) / total_qty
        existing.quantity = round(total_qty, 2)
        existing.buy_price = round(avg_price, 2)
        existing.updated_at = datetime.now(timezone.utc)
        return {"message": f"Updated position for {ticker}", "action": "averaged", "ticker": ticker}
    else:
        new_pos = PortfolioPosition(
            user_id=current_user.id,
            ticker=ticker,
            quantity=req.quantity,
            buy_price=req.buy_price,
        )
        db.add(new_pos)
        return {"message": f"Added {ticker} to portfolio", "action": "added", "ticker": ticker}


@router.delete("/{ticker}")
async def remove_position(
    ticker: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a stock from the portfolio."""
    ticker = ticker.upper()
    result = await db.execute(
        select(PortfolioPosition).where(
            PortfolioPosition.user_id == current_user.id,
            PortfolioPosition.ticker == ticker,
        )
    )
    existing = result.scalar_one_or_none()
    if not existing:
        raise HTTPException(status_code=404, detail=f"{ticker} not in portfolio.")
    await db.execute(
        delete(PortfolioPosition).where(
            PortfolioPosition.user_id == current_user.id,
            PortfolioPosition.ticker == ticker,
        )
    )
    return {"message": f"Removed {ticker} from portfolio", "ticker": ticker}
