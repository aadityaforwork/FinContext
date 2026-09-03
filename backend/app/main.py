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
    brief_email as brief_email_router,
    onboarding as onboarding_router,
    prompt_monitor as prompt_monitor_router,
    accuracy_monitor as accuracy_monitor_router,
    grounding_monitor as grounding_monitor_router,
    miss_fixtures as miss_fixtures_router,
    prompt_drafter as prompt_drafter_router,
    debug_memory,
)
from app.agents import base as agents_base
from app.core.config import settings
from app.db import init_db

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
app.include_router(brief_email_router.router)
app.include_router(onboarding_router.router)
app.include_router(prompt_monitor_router.router)
app.include_router(accuracy_monitor_router.router)
app.include_router(grounding_monitor_router.router)
app.include_router(miss_fixtures_router.router)
app.include_router(prompt_drafter_router.router)
app.include_router(debug_memory.router)


@app.on_event("startup")
async def _init_cache_tables():
    """Create the SQLAlchemy-managed tables — in practice, `llm_cache`.

    `init_db()` existed but was never called from anywhere, so the `llm_cache`
    table was never created. Every `llm_cache.get`/`set` therefore raised, got
    swallowed by that module's own try/except, and logged a warning — meaning
    the "persistent, shared across workers, survives restart" cache tier has
    been a silent no-op for the crew paths, and would have been for the
    dashboard endpoints now routed through response_cache.put_shared too.

    `create_all` is `checkfirst=True`, so it only creates what's missing and
    never alters an existing table — the Supabase-managed `users` / `watchlist`
    / `portfolio` tables (owned by supabase/migrations/*.sql, with RLS) are left
    untouched. Never raises: a cache-table failure must not block boot, since
    every caller already degrades to recomputing.

    NOTE: this only buys real persistence when DATABASE_URL points at Postgres.
    Unset, app/db falls back to SQLite on an ephemeral disk.
    """
    try:
        await init_db()
        logger.info("DB tables ready (llm_cache persistent tier available)")
    except Exception as e:
        logger.warning("init_db failed — llm_cache falls back to in-process only: %s", e)


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


_sentry_flush_task: asyncio.Task | None = None


async def _sentry_log_flush_loop() -> None:
    """Periodically call sentry_sdk.flush() so Sentry Logs actually ship.

    Sentry Logs (enable_logs=True) batches client-side and is NOT delivered by
    the same eager transport as error/issue events — confirmed 2026-08-15 via
    a live A/B/C test: a one-shot script that logged once and called
    sentry_sdk.flush() explicitly delivered every time; a process that logged
    once and stayed alive for 90s with no flush() call never delivered
    anything, even after exiting normally. This app's uvicorn process runs
    forever and never exits under normal operation, so without this loop every
    logger.info()/.warning() across the whole app accumulates in Sentry's Logs
    buffer and never ships. Error/issue capture (Sentry Issues) is unaffected
    by any of this — it already shipped immediately without a flush, which is
    exactly what made the Logs gap easy to miss.

    Runs on a worker thread (sentry_sdk.flush is a blocking call) so a slow or
    stalled flush can't stall the event loop. Never raises — a flush failure
    must not crash the periodic loop or take down the app.
    """
    interval = settings.SENTRY_LOG_FLUSH_INTERVAL_S
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(sentry_sdk.flush, timeout=5)
        except Exception:
            logger.exception("periodic sentry_sdk.flush() failed")


@app.on_event("startup")
async def _start_sentry_log_flush_loop():
    """Start the periodic Sentry Logs flush loop — no-op if Sentry is unset."""
    global _sentry_flush_task
    if not settings.SENTRY_DSN:
        return
    _sentry_flush_task = asyncio.create_task(_sentry_log_flush_loop())
    logger.info(
        "Sentry Logs periodic flush loop started (every %ss)", settings.SENTRY_LOG_FLUSH_INTERVAL_S
    )


@app.on_event("shutdown")
async def _stop_sentry_log_flush_loop():
    """Cancel the flush loop and do one last flush so a graceful shutdown
    doesn't strand whatever logs accumulated since the last periodic flush."""
    global _sentry_flush_task
    if _sentry_flush_task is not None:
        _sentry_flush_task.cancel()
        _sentry_flush_task = None
    if settings.SENTRY_DSN:
        try:
            await asyncio.to_thread(sentry_sdk.flush, timeout=5)
        except Exception:
            logger.exception("final sentry_sdk.flush() on shutdown failed")


@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "healthy", "version": "0.5.0"}
