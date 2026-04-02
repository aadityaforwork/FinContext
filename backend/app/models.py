"""
Pydantic Models / Schemas
=========================
Data models for the FinContext API.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import date


class StockInfo(BaseModel):
    """Basic stock metadata shown in the watchlist."""
    ticker: str
    name: str
    sector: str
    current_price: float
    change_percent: float
    market_cap_cr: Optional[float] = None  # Market cap in ₹ Crores


class PricePoint(BaseModel):
    """Single data point for charting."""
    date: str  # ISO date string
    open: float
    high: float
    low: float
    close: float
    volume: int


class PriceHistoryResponse(BaseModel):
    """Response for GET /api/stocks/{ticker}/price"""
    ticker: str
    name: str
    currency: str = "INR"
    data: list[PricePoint]


class AnalysisRequest(BaseModel):
    """Request body for POST /api/stocks/{ticker}/analyze"""
    # Optional user query to guide the analysis
    query: Optional[str] = Field(
        default=None,
        description="Optional natural-language question about this stock"
    )
    # Number of context docs to retrieve from the vector store
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of context documents to retrieve"
    )


class NewsContext(BaseModel):
    """A single retrieved news/context chunk (simulates vector search result)."""
    source: str
    headline: str
    snippet: str
    relevance_score: float
    published_date: str


class AnalysisResponse(BaseModel):
    """Response for POST /api/stocks/{ticker}/analyze"""
    ticker: str
    name: str
    analysis: str  # The synthesized paragraph from the "LLM"
    context_sources: list[NewsContext]
    model_version: str = "mock-rag-v0.1"
    # TODO: Add MLflow run_id once experiment tracking is integrated
    # mlflow_run_id: Optional[str] = None
