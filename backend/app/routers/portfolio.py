"""
Portfolio P&L enrichment endpoint.
Accepts positions array from the frontend (stored in Supabase),
fetches live prices, computes P&L, and returns a full summary.
No auth required — scoping is done on the frontend via Supabase.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter
from pydantic import BaseModel
from cachetools import TTLCache
import yfinance as yf
from app.nse_universe import TICKER_TO_YF, TICKER_TO_META, resolve_yf_symbol
from app.services import yf_safe

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

# Positive cache 3 min; negative caches split between permanent (delisted —
# 24h so we don't re-pay yfinance retry tax) and transient (network hiccup,
# 60s so we recover promptly).
_price_cache: TTLCache = TTLCache(maxsize=300, ttl=180)
_price_neg_perm: TTLCache = TTLCache(maxsize=500, ttl=yf_safe.NEG_TTL_PERMANENT_S)
_price_neg_transient: TTLCache = TTLCache(maxsize=300, ttl=yf_safe.NEG_TTL_TRANSIENT_S)
_price_executor = ThreadPoolExecutor(max_workers=12)


class PositionIn(BaseModel):
    ticker: str
    quantity: float
    buy_price: float


class EnrichRequest(BaseModel):
    positions: list[PositionIn]


def _fetch_price_inner(yf_symbol: str) -> tuple[float | None, float | None] | None:
    """Pure yfinance call inside yf_safe pool. Returns:
      • (price, change_pct) on success
      • None when fast_info returned but had no usable data — signals delisted
        so the outer caller caches as permanent (24h).

    Critically does NOT catch exceptions: if fast_info access raises (rate
    limit, network), let it propagate so yf_safe.classify_error can pattern-
    match the message and pick the right cache TTL (transient 60s for rate-
    limited tickers, NOT permanent 24h — that bug just poisoned every real
    ticker for an entire day when Yahoo rate-limited once mid-fanout).
    """
    info = yf.Ticker(yf_symbol).fast_info
    price = float(info.last_price) if hasattr(info, "last_price") else None
    prev = float(info.previous_close) if hasattr(info, "previous_close") else None
    if price is None or prev is None or prev == 0:
        return None
    return (round(price, 2), round((price - prev) / prev * 100, 2))


def _get_live_price(ticker: str) -> tuple[float | None, float | None]:
    """Returns (price, change_percent). None values mean we couldn't get live data —
    UI distinguishes "no data" (renders as "—") from a real zero.

    Hardened with yf_safe — 5s wall timeout, 24h cache for delisted symbols.
    """
    if ticker in _price_cache:
        return _price_cache[ticker]
    if ticker in _price_neg_perm or ticker in _price_neg_transient:
        return (None, None)
    yf_symbol = resolve_yf_symbol(ticker)
    if not yf_symbol:
        _price_neg_perm[ticker] = True
        return (None, None)

    result, ok = yf_safe.run_with_timeout(_fetch_price_inner, yf_symbol, timeout_s=5.0)
    if not ok:
        exc = result if isinstance(result, Exception) else None
        kind = yf_safe.classify_error(exc, None if exc is None else "__sentinel__")
        if kind == "permanent":
            _price_neg_perm[ticker] = True
        else:
            _price_neg_transient[ticker] = True
        return (None, None)
    if result is None:
        _price_neg_perm[ticker] = True
        return (None, None)
    _price_cache[ticker] = result
    return result


@router.post("/enrich")
async def enrich_portfolio(req: EnrichRequest):
    """Enrich positions with live prices and return a full P&L summary."""
    positions = []
    total_invested = 0.0
    current_value = 0.0
    day_change = 0.0

    tickers = [p.ticker.upper() for p in req.positions]
    loop = asyncio.get_running_loop()
    quotes = await asyncio.gather(*[
        loop.run_in_executor(_price_executor, _get_live_price, t) for t in tickers
    ]) if tickers else []
    quote_map = dict(zip(tickers, quotes))

    for pos in req.positions:
        ticker = pos.ticker.upper()
        meta = TICKER_TO_META.get(ticker, {"name": ticker, "sector": "Unknown"})
        price, change_pct = quote_map.get(ticker, (None, None))
        # Fall back to buy_price for invested-value math when live price is missing,
        # but keep change_percent as None so UI shows "—" not "+0.0%".
        effective_price = price if price is not None else pos.buy_price

        invested = pos.quantity * pos.buy_price
        current = pos.quantity * effective_price
        pnl = current - invested
        pnl_pct = (pnl / invested * 100) if invested else 0.0

        total_invested += invested
        current_value += current
        if change_pct is not None:
            day_change += current * (change_pct / 100)

        positions.append({
            "ticker": ticker,
            "name": meta["name"],
            "sector": meta["sector"],
            "quantity": pos.quantity,
            "buy_price": pos.buy_price,
            "current_price": effective_price,
            "change_percent": change_pct,            # ← was missing entirely
            "invested_value": round(invested, 2),
            "current_value": round(current, 2),
            "pnl": round(pnl, 2),
            "pnl_percent": round(pnl_pct, 2),
        })

    total_pnl = current_value - total_invested
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested else 0.0
    day_change_pct = (day_change / current_value * 100) if current_value else 0.0

    allocation: dict[str, float] = {}
    for p in positions:
        allocation[p["sector"]] = allocation.get(p["sector"], 0) + p["current_value"]
    allocation_list = [
        {"sector": k, "value": round(v, 2), "percent": round(v / current_value * 100, 1) if current_value else 0}
        for k, v in sorted(allocation.items(), key=lambda x: -x[1])
    ]

    return {
        "total_invested": round(total_invested, 2),
        "current_value": round(current_value, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_percent": round(total_pnl_pct, 2),
        "day_change": round(day_change, 2),
        "day_change_percent": round(day_change_pct, 2),
        "holdings_count": len(positions),
        "positions": positions,
        "allocation": allocation_list,
    }
