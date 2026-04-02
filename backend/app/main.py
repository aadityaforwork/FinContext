"""
FinContext API — Main Application
==================================
AI-powered contextual analysis for Indian equities.

Entry point for the FastAPI application.
Run with: uvicorn app.main:app --reload --port 8000
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import stocks, market, portfolio, watchlist, analysis, zerodha, portfolio_intelligence, global_news, company_data
from app.db import init_db


# ---------------------------------------------------------------------------
# Lifespan: startup / shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB tables on startup, seed default watchlist."""
    await init_db()
    await _seed_default_watchlist()
    yield  # app runs here
    # shutdown: nothing to clean up for SQLite


async def _seed_default_watchlist():
    """Pre-populate watchlist with default tickers if table is empty."""
    from sqlalchemy import select, func
    from app.db import async_session
    from app.db.models import WatchlistItem

    async with async_session() as session:
        result = await session.execute(select(func.count(WatchlistItem.id)))
        count = result.scalar()
        if count == 0:
            defaults = ["RECLTD", "RVNL", "HBLPOWER", "TATAMOTORS", "RELIANCE"]
            for ticker in defaults:
                session.add(WatchlistItem(ticker=ticker))
            await session.commit()


# ---------------------------------------------------------------------------
# App Configuration
# ---------------------------------------------------------------------------

app = FastAPI(
    title="FinContext API",
    description=(
        "AI-powered contextual analysis engine for Indian mid-cap and large-cap equities. "
        "Explains why stocks are moving by synthesizing global macro trends, "
        "local news, and sector updates using a RAG pipeline."
    ),
    version="0.3.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS Middleware — allow Next.js frontend
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Router Registration
# ---------------------------------------------------------------------------

app.include_router(stocks.router)
app.include_router(market.router)
app.include_router(portfolio.router)
app.include_router(watchlist.router)
app.include_router(analysis.router)
app.include_router(zerodha.router)
app.include_router(portfolio_intelligence.router)
app.include_router(global_news.router)
app.include_router(company_data.router)

# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["system"])
async def health_check():
    """Health check endpoint for monitoring and load balancers."""
    return {
        "status": "healthy",
        "version": "0.3.0",
        "service": "fincontext-api",
        "database": "sqlite",
    }
