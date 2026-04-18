"""
FinContext API — Main Application
==================================
AI-powered contextual analysis for Indian equities.

Run with: uvicorn app.main:app --reload --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import (
    stocks,
    market,
    portfolio,
    watchlist,
    analysis,
    zerodha,
    portfolio_intelligence,
    global_news,
    company_data,
)
from app.core.config import settings

app = FastAPI(
    title="FinContext API",
    description="AI-powered contextual analysis engine for Indian equities.",
    version="0.5.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stocks.router)
app.include_router(market.router)
app.include_router(portfolio.router)
app.include_router(watchlist.router)
app.include_router(analysis.router)
app.include_router(zerodha.router)
app.include_router(portfolio_intelligence.router)
app.include_router(global_news.router)
app.include_router(company_data.router)


@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "healthy", "version": "0.5.0"}
