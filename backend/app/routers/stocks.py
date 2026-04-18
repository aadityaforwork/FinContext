"""
Stocks Router
=============
API endpoints for stock data and analysis.
Uses live data from yfinance. Supports browsing the full NSE universe
and the original watchlist tickers.
"""

from fastapi import APIRouter, HTTPException, Query
from app.models import (
    StockInfo,
    PriceHistoryResponse,
    PricePoint,
    AnalysisRequest,
    AnalysisResponse,
    NewsContext,
)
from app.seed_data import STOCKS, PRICE_HISTORIES
from app.nse_universe import (
    NSE_STOCKS,
    TICKER_TO_YF,
    TICKER_TO_META,
    ALL_SECTORS,
    search_stocks,
)
from app.services.data_ingestion import retrieve_context
from app.services.llm_engine import generate_analysis

import asyncio
import yfinance as yf
from cachetools import TTLCache
from concurrent.futures import ThreadPoolExecutor
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stocks", tags=["stocks"])

# Cache for browse/search prices (10 min TTL — list views don't need tick-level freshness)
_browse_cache = TTLCache(maxsize=2000, ttl=600)
_quote_executor = ThreadPoolExecutor(max_workers=24)


def _get_quote(ticker: str) -> tuple[float, float]:
    """Get (price, change_pct) for any NSE universe ticker."""
    cache_key = f"browse_{ticker}"
    if cache_key in _browse_cache:
        return _browse_cache[cache_key]

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
        _browse_cache[cache_key] = result
        return result
    except Exception as e:
        logger.warning(f"Quote fetch failed for {ticker}: {e}")
        return (0.0, 0.0)


def _get_history(ticker: str, period: str = "1mo") -> list[dict]:
    """Get historical OHLCV for any NSE universe ticker."""
    yf_symbol = TICKER_TO_YF.get(ticker)
    if not yf_symbol:
        return []
    try:
        stock = yf.Ticker(yf_symbol)
        hist = stock.history(period=period)
        if hist.empty:
            return []
        data = []
        for idx, row in hist.iterrows():
            data.append({
                "date": idx.strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            })
        return data
    except Exception as e:
        logger.warning(f"History fetch failed for {ticker}: {e}")
        return []


# -----------------------------------------------------------------------
# Browse & Search
# -----------------------------------------------------------------------
@router.get("/search")
async def search_nse_stocks(
    q: str = Query("", description="Search query"),
    sector: str = Query(None, description="Filter by sector"),
    limit: int = Query(50, le=150),
):
    """Search the NSE stock universe by name/ticker with optional sector filter."""
    results = search_stocks(query=q, sector=sector, limit=limit)
    if not results:
        return []

    loop = asyncio.get_running_loop()
    quotes = await asyncio.gather(*[
        loop.run_in_executor(_quote_executor, _get_quote, s["ticker"])
        for s in results
    ])
    return [
        {**s, "current_price": p, "change_percent": c}
        for s, (p, c) in zip(results, quotes)
    ]


@router.get("/sectors")
async def get_sectors():
    """Get list of all available sectors for filtering."""
    return ALL_SECTORS


# -----------------------------------------------------------------------
# Existing Endpoints (updated for full NSE universe)
# -----------------------------------------------------------------------
@router.get("/{ticker}/price", response_model=PriceHistoryResponse)
async def get_stock_price_history(ticker: str):
    """Get historical price data for any NSE ticker."""
    ticker = ticker.upper()

    if ticker not in TICKER_TO_YF:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found.")

    meta = TICKER_TO_META.get(ticker, {"name": ticker, "sector": "Unknown"})
    live_data = _get_history(ticker, period="1mo")

    if live_data:
        return PriceHistoryResponse(
            ticker=ticker,
            name=meta.get("name", ticker),
            data=[PricePoint(**p) for p in live_data],
        )

    # Fallback to seed data if available
    seed_data = PRICE_HISTORIES.get(ticker, [])
    return PriceHistoryResponse(
        ticker=ticker,
        name=meta.get("name", ticker),
        data=[PricePoint(**p) for p in seed_data],
    )


@router.post("/{ticker}/analyze", response_model=AnalysisResponse)
async def analyze_stock(ticker: str, request: AnalysisRequest = AnalysisRequest()):
    """
    Analyze any NSE stock using real news data:
    1. Retrieve real news context from Google News RSS
    2. Generate a synthesized analysis
    """
    ticker = ticker.upper()

    if ticker not in TICKER_TO_YF:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found.")

    meta = TICKER_TO_META.get(ticker, {"name": ticker, "sector": "Unknown"})

    # Ensure seed data has this ticker's info for the LLM engine
    price, change = _get_quote(ticker)
    STOCKS[ticker] = {
        "name": meta.get("name", ticker),
        "sector": meta.get("sector", "Unknown"),
        "current_price": price,
        "change_percent": change,
    }

    # Step 1: RETRIEVAL
    context_docs = retrieve_context(
        ticker=ticker,
        query=request.query,
        top_k=request.top_k,
    )

    # Step 2: GENERATION
    analysis_text = generate_analysis(
        ticker=ticker,
        context_docs=context_docs,
    )

    return AnalysisResponse(
        ticker=ticker,
        name=meta.get("name", ticker),
        analysis=analysis_text,
        context_sources=[NewsContext(**doc) for doc in context_docs],
    )
