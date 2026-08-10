"""
FinContext MCP Server
======================
Exposes two read-only tools backed by the FinContext backend API:

  pre_trade_check(ticker)   — deterministic PASS/CAUTION/FAIL scorecard, no LLM
  get_stock_context(ticker) — grounded snapshot + peer benchmark + news, no LLM

Both are thin HTTP wrappers over the backend's own /api/analysis/pre-trade-check
and /api/analysis/context routes. No domain logic lives here — same rule
backend/app/agents/tools.py follows for CrewAI tool wrappers, applied to this
process too.

Why only two tools: this is deliberately the "free, top-of-funnel" MCP surface
from the viability assessment, not the whole product. Portfolio-aware flows
(Morning Brief, News Feed, Movers) need holdings + SSE streaming and don't fit
a stateless request/response MCP tool — see the plan doc for the reasoning.

COMPLIANCE — read before editing tool descriptions:
FinContext operates without SEBI Research Analyst registration (see
STRATEGY.md / AGENTS.md rule 4 in the main repo). Every tool docstring below
is also the tool's MCP description, and each one explicitly tells the calling
model not to turn a factor checklist into buy/sell/target-price language.
Don't soften or drop that instruction when editing — it's the only lever this
server has over how a host model phrases its answer, since the backend's
`disclaimer` field travels in the payload but doesn't bind the host's prose.

Config (env vars):
  FINCONTEXT_API_BASE  Base URL of the backend API, e.g.
                        https://fin-context.vercel.app/_/backend
                        Defaults to http://localhost:8000 for local dev
                        against `uvicorn app.main:app` in ../backend.
  FINCONTEXT_API_KEY    Optional. Sent as X-API-Key. Without it, calls land
                        in the anonymous rate-limit tier (30/min per IP —
                        see backend/app/core/rate_limit.py); fine for light,
                        single-user use. Set it for a higher shared quota.

Run directly for local testing:
  python server.py
Or install per README.md and point Claude Desktop / Cursor's MCP config at it.
"""

from __future__ import annotations

import os

import httpx
from mcp.server.fastmcp import FastMCP

API_BASE = os.environ.get("FINCONTEXT_API_BASE", "http://localhost:8000").rstrip("/")
API_KEY = os.environ.get("FINCONTEXT_API_KEY")

mcp = FastMCP("fincontext")


async def _post(path: str, ticker: str) -> dict:
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(f"{API_BASE}{path}", json={"ticker": ticker}, headers=headers)
    except httpx.RequestError as e:
        return {"error": f"Could not reach FinContext backend at {API_BASE}: {e}"}

    if resp.status_code == 404:
        return {"error": f"Ticker '{ticker}' not found in FinContext's NSE universe."}
    if resp.status_code == 429:
        return {
            "error": "Rate limited. Set FINCONTEXT_API_KEY for a higher shared quota, "
                     "or wait a minute and retry."
        }
    if resp.status_code == 401:
        return {"error": "FINCONTEXT_API_KEY was rejected by the backend — check the value."}
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
async def pre_trade_check(ticker: str) -> dict:
    """Run a deterministic pre-trade checklist for one NSE-listed Indian equity.

    Six checks, each PASS/CAUTION/FAIL against a fixed rule, no LLM involved:
    RSI (overbought/oversold), distance from the 20-day moving average,
    volume vs its 20-day average, valuation (P/E) vs sector peer median,
    position within the 52-week range, and primary trend vs the 50-day
    moving average. Returns a top-line pass/caution/fail count.

    This is a checklist, not a verdict — it never says "buy" or "don't buy",
    and you should not either. Present the individual factors and their
    `why` explanations; do not compress them into a buy/sell recommendation
    or a target price. This is educational/informational output, not
    investment advice — surface the response's `disclaimer` field to the
    user rather than paraphrasing it away.

    Args:
        ticker: NSE ticker symbol, e.g. "RELIANCE", "TCS", "HDFCBANK".
    """
    return await _post("/api/analysis/pre-trade-check", ticker.strip().upper())


@mcp.tool()
async def get_stock_context(ticker: str) -> dict:
    """Fetch grounded, real-data context for one NSE-listed Indian equity.

    No LLM call, no narrative synthesis — this is the same context block
    FinContext's own AI features (Deep Dive, DD Agent) are built from, handed
    to you directly: live price + fundamentals snapshot, sector-peer medians
    and this stock's percentile rank against them, rule-based (non-LLM)
    strengths/concerns each citing the exact field that backs it, same-sector
    peers with higher ROE, and recent news headlines.

    Use this as source material for your own analysis. Every numeric claim
    you make from this data should be traceable back to a field in the
    response. Do not present it as a buy/sell recommendation or invent a
    target price — this is educational/informational output. Surface the
    response's `disclaimer` field to the user rather than paraphrasing it away.

    Args:
        ticker: NSE ticker symbol, e.g. "RELIANCE", "TCS", "HDFCBANK".
    """
    return await _post("/api/analysis/context", ticker.strip().upper())


if __name__ == "__main__":
    mcp.run()
