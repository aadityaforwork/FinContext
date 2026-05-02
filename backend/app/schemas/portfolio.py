"""Portfolio request/response shapes — single source of truth.

Today the same PositionIn class is re-declared in routers/portfolio.py,
routers/portfolio_intelligence.py, and grounding callers. New code should
import this one and stop redeclaring.
"""

from pydantic import BaseModel


class PositionIn(BaseModel):
    """A holding as submitted from the client (Supabase-scoped)."""
    ticker: str
    quantity: float
    buy_price: float


class SectorAllocation(BaseModel):
    sector: str
    value: float
    percent: float


class EnrichedPosition(BaseModel):
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


class PortfolioSummary(BaseModel):
    total_invested: float
    current_value: float
    total_pnl: float
    total_pnl_percent: float
    day_change: float
    day_change_percent: float
    holdings_count: int
    positions: list[EnrichedPosition]
    allocation: list[SectorAllocation]
