"""
Agent tools — thin wrappers exposing existing services to CrewAI agents.

Why this exists: CrewAI agents need callables decorated with @tool to use as
their action surface. Rather than implement domain logic here, every tool is
a one-line pass-through to a service. This keeps:
  - services/ framework-agnostic (drop CrewAI later? services don't care)
  - tools/ as a thin adapter (one place to change tool signatures)
  - zero duplicated logic

Phase A surface is intentionally minimal — Narrative-to-Numbers needs no
external tools, so all we expose are stock-info helpers that later crews
(Deep Dive, Portfolio Intelligence) will consume.
"""

from __future__ import annotations

import json
import logging

from app.services import fundamentals, market_data

logger = logging.getLogger(__name__)


def _json(payload: object) -> str:
    """CrewAI tools must return strings. JSON keeps structure for the LLM to parse."""
    return json.dumps(payload, default=str)


# Lazy-import the @tool decorator so importing this module doesn't require crewai.
def _build_tools():
    from crewai.tools import tool  # type: ignore

    @tool("get_company_overview")
    def get_company_overview(ticker: str) -> str:
        """Return a JSON object with name, sector, current_price, PE, PB, ROE, debt_to_equity, 52-week range, market cap, and a short business description for the given NSE ticker. Use this to ground any claim about a company's current valuation or fundamentals."""
        try:
            return _json(fundamentals.get_overview(ticker))
        except LookupError as e:
            return _json({"error": str(e)})
        except Exception as e:
            logger.exception("get_company_overview tool failed")
            return _json({"error": f"fetch_failed: {e}"})

    @tool("get_company_ratios")
    def get_company_ratios(ticker: str) -> str:
        """Return a JSON object of valuation, profitability, growth, financial-health, and dividend ratios for the given NSE ticker. Use this when peer or trend comparisons are needed."""
        try:
            return _json(fundamentals.get_ratios(ticker))
        except LookupError as e:
            return _json({"error": str(e)})

    @tool("get_company_peers")
    def get_company_peers(ticker: str) -> str:
        """Return a JSON list of same-sector peer companies with their PE, PB, ROE, profit margin, and debt-to-equity. Use this to ground percentile / peer-rank claims."""
        try:
            return _json(fundamentals.get_peers(ticker))
        except LookupError as e:
            return _json({"error": str(e)})

    @tool("get_price_history")
    def get_price_history(ticker: str, period: str = "1mo") -> str:
        """Return a JSON list of OHLCV bars for the ticker over the given period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, max). Use to ground momentum or drawdown claims."""
        try:
            data = market_data.get_price_history(ticker, period)
            return _json({"ticker": ticker, "period": period, "data": data})
        except Exception as e:
            return _json({"error": f"fetch_failed: {e}"})

    @tool("get_market_indices")
    def get_market_indices() -> str:
        """Return a JSON list of NIFTY 50, SENSEX, NIFTY MIDCAP, INR/USD with current value and change percent. Use to ground market-wide claims."""
        try:
            return _json(market_data.get_market_indices())
        except Exception as e:
            return _json({"error": f"fetch_failed: {e}"})

    return {
        "get_company_overview": get_company_overview,
        "get_company_ratios": get_company_ratios,
        "get_company_peers": get_company_peers,
        "get_price_history": get_price_history,
        "get_market_indices": get_market_indices,
    }


_tools_cache = None


def get_tools() -> dict:
    """Return the dict of tool name → tool callable. Lazy so missing crewai doesn't break unrelated imports."""
    global _tools_cache
    if _tools_cache is None:
        _tools_cache = _build_tools()
    return _tools_cache
