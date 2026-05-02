"""Market data shapes — price history, OHLCV bars."""

from pydantic import BaseModel


class OHLCVBar(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class PriceSeries(BaseModel):
    ticker: str
    period: str
    data: list[OHLCVBar]
