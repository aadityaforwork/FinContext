"""Risk-metric and benchmark shapes (populated in Phase 2 — defined now so
services and routers built later can import canonical types from day one)."""

from pydantic import BaseModel


class RiskMetrics(BaseModel):
    """Portfolio-level numeric analytics (§4.1)."""
    volatility_annualized: float | None = None
    beta_vs_nifty50: float | None = None
    max_drawdown_1y: float | None = None
    max_drawdown_3y: float | None = None
    max_drawdown_5y: float | None = None
    sharpe_ratio: float | None = None
    risk_free_rate_used: float = 0.06
    sample_size_days: int | None = None


class BenchmarkSeries(BaseModel):
    """Returns for one benchmark over standard horizons (§4.2)."""
    label: str
    return_1y_percent: float | None = None
    return_3y_percent: float | None = None
    return_5y_percent: float | None = None


class BenchmarkResult(BaseModel):
    """Portfolio TWR/XIRR vs index benchmarks."""
    portfolio: BenchmarkSeries
    benchmarks: list[BenchmarkSeries]
    xirr_percent: float | None = None
    alpha_1y: float | None = None
    information_ratio: float | None = None


class CorrelationMatrix(BaseModel):
    """Pairwise daily-return correlations across holdings (§4.7)."""
    tickers: list[str]
    matrix: list[list[float]]
    high_correlation_pairs: list[dict]


class ConcentrationReport(BaseModel):
    """Concentration metrics — sector HHI, top-N share (§4.1, §4.7)."""
    sector_hhi: float | None = None
    top_holding_pct: float | None = None
    top_3_holdings_pct: float | None = None
    top_sector_pct: float | None = None
    flagged_clusters: list[str] = []
