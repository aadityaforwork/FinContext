"""
FinContext API — Main Application
==================================
AI-powered contextual analysis for Indian equities.

Run with: uvicorn app.main:app --reload --port 8000
"""

import asyncio
import logging

import sentry_sdk
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
    risk,
    social as social_router,
    embeddings as embeddings_router,
    outcomes as outcomes_router,
    telegram as telegram_router,
    onboarding as onboarding_router,
)
from app.agents import base as agents_base
from app.core.config import settings

logger = logging.getLogger("uvicorn.error")
# Print loaded CORS config at boot — visible in Render logs. Helps diagnose
# "Access-Control-Allow-Origin missing" errors caused by env var typos.
logger.info("CORS_ORIGINS loaded: %r", settings.CORS_ORIGINS)
logger.info("CORS_ORIGIN_REGEX loaded: %r", settings.CORS_ORIGIN_REGEX)

# Sentry — no-op locally/in CI unless SENTRY_DSN is set. Project:
# fincontext-backend (org compute-ji) — see CLAUDE.md "MCP connectors".
# Initialized before FastAPI app construction so import-time/startup errors
# are captured too, not just request-time ones.
#
# enable_logs=True: without it, Sentry's Logs product stays empty forever
# regardless of traffic — it defaults to False (sentry_sdk >=2.35) and isn't
# implied by setting a DSN. Once on, every stdlib `logging` call at INFO+
# across the app (this file, llm_trace.py, ai_client.py, etc.) ships to
# Sentry Logs via the auto-enabled logging integration — no per-call-site
# changes needed. Diagnosed 2026-08-11: DSN/ingestion/errors were already
# working end-to-end (verified with a live test event), this flag was the
# actual reason "no logs" specifically.
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_ENVIRONMENT,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=False,  # portfolio/financial data — never auto-attach request bodies/user data
        enable_logs=True,
    )
    logger.info("Sentry initialized (env=%s, logs enabled)", settings.SENTRY_ENVIRONMENT)
else:
    logger.info("SENTRY_DSN not set — Sentry disabled")

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
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/_debug/cors", tags=["system"])
async def debug_cors():
    """Returns the loaded CORS config so you can verify env-var values from Render
    without redeploying. Safe to keep enabled — exposes only allowed origins, no secrets."""
    return {
        "allow_origins": settings.CORS_ORIGINS,
        "allow_origin_regex": settings.CORS_ORIGIN_REGEX,
    }

app.include_router(stocks.router)
app.include_router(market.router)
app.include_router(portfolio.router)
app.include_router(watchlist.router)
app.include_router(analysis.router)
app.include_router(zerodha.router)
app.include_router(portfolio_intelligence.router)
app.include_router(global_news.router)
app.include_router(company_data.router)
app.include_router(risk.router)
app.include_router(social_router.router)
app.include_router(embeddings_router.router)
app.include_router(outcomes_router.router)
app.include_router(telegram_router.router)
app.include_router(onboarding_router.router)


@app.on_event("startup")
async def _prewarm_agents():
    """Build the CrewAI LLM singleton(s) at boot instead of on the first request.

    Without this, agents/base.py's lazy singleton pays SDK-import + client-
    construction cost inside whichever user's request happens to hit
    narrative-impact or risk-brief first — directly inflating that request's
    time-to-first-response. Runs on a worker thread so a slow/misbehaving
    import can't stall the event loop past startup; never raises (prewarm()
    already swallows and logs internally) so a missing GROQ_API_KEY or
    crewai install can't block boot.
    """
    await asyncio.to_thread(agents_base.prewarm)


@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "healthy", "version": "0.5.0"}
