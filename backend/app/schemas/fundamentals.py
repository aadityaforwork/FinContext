"""Company fundamentals shapes — backing services/fundamentals.py.

These mirror the dict shapes the company_data router returns today; declaring
them here lets future callers (deep-dive synthesis, screener) use typed objects
without redefining fields.
"""

from pydantic import BaseModel


class CompanyOverview(BaseModel):
    ticker: str
    name: str
    sector: str
    industry: str | None = None
    current_price: float
    change_percent: float
    previous_close: float | None = None
    market_cap: float | None = None
    market_cap_formatted: str | None = None
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    eps: float | None = None
    dividend_yield: float | None = None
    book_value: float | None = None
    face_value: float | None = None
    roe: float | None = None
    roce: float | None = None
    debt_to_equity: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    volume: int | None = None
    avg_volume: int | None = None
    description: str | None = None


class FinancialStatements(BaseModel):
    ticker: str
    period: str
    income_statement: dict
    balance_sheet: dict
    cash_flow: dict


class RatioBundle(BaseModel):
    ticker: str
    valuation: dict
    profitability: dict
    growth: dict
    financial_health: dict
    dividends: dict


class PeerRow(BaseModel):
    ticker: str
    name: str
    current_price: float
    market_cap: str | None = None
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    roe: float | None = None
    profit_margin: float | None = None
    debt_to_equity: float | None = None
    dividend_yield: float | None = None
    is_target: bool = False


class PeerComparison(BaseModel):
    ticker: str
    sector: str
    peers: list[PeerRow]


class Shareholding(BaseModel):
    ticker: str
    major_holders: list[dict]
    top_institutions: list[dict]
