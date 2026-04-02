"""
Market Router
=============
API endpoints for market-wide data (indices, macro).
"""

from fastapi import APIRouter
from app.services.market_data import get_market_indices

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/indices")
async def market_indices():
    """
    Get live market index values: NIFTY 50, SENSEX, NIFTY MIDCAP, INR/USD.
    Data from yfinance with 3-minute cache.
    """
    return get_market_indices()
