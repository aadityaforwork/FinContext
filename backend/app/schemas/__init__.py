"""
Shared Pydantic schemas
=======================

Canonical request/response shapes used across routers and services.
Defining them once here prevents the same fields being redeclared inline
in every router (a recurring duplication source in this codebase).

Existing legacy models in app.models are kept for backward compatibility;
new modules should import from app.schemas instead.
"""

from app.schemas.market import OHLCVBar, PriceSeries
from app.schemas.portfolio import (
    PositionIn,
    EnrichedPosition,
    SectorAllocation,
    PortfolioSummary,
)
from app.schemas.risk import (
    RiskMetrics,
    BenchmarkSeries,
    BenchmarkResult,
    CorrelationMatrix,
    ConcentrationReport,
)
from app.schemas.fundamentals import (
    CompanyOverview,
    FinancialStatements,
    RatioBundle,
    PeerRow,
    PeerComparison,
    Shareholding,
)

__all__ = [
    "OHLCVBar",
    "PriceSeries",
    "PositionIn",
    "EnrichedPosition",
    "SectorAllocation",
    "PortfolioSummary",
    "RiskMetrics",
    "BenchmarkSeries",
    "BenchmarkResult",
    "CorrelationMatrix",
    "ConcentrationReport",
    "CompanyOverview",
    "FinancialStatements",
    "RatioBundle",
    "PeerRow",
    "PeerComparison",
    "Shareholding",
]
