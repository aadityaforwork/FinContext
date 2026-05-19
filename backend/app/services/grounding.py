"""
Grounding Service
=================
Builds structured, real-data CONTEXT blocks that back every grounded LLM call.

Philosophy: the LLM must never invent financial numbers. Every analytical claim
has to reference a path inside the context dict produced here. This mirrors what
Tickertape/Screener do (peer-percentile scoring, rule-based pros/cons) but lets
the LLM synthesize the narrative on top of verified facts.

Public:
    build_stock_context(ticker) -> dict
    build_portfolio_context(holdings) -> dict
    build_market_context() -> dict
    build_movers_context(holdings) -> dict
"""

from __future__ import annotations

import logging
import re
import statistics
from urllib.parse import quote
from typing import Any

import feedparser
import yfinance as yf
from cachetools import TTLCache

from app.nse_universe import TICKER_TO_META, TICKER_TO_YF, NSE_STOCKS, resolve_yf_symbol
from app.services import data_ingestion, market_flows, news_sources, policy_feeds, technicals, vector_store, yf_safe

logger = logging.getLogger(__name__)

_context_cache: TTLCache = TTLCache(maxsize=200, ttl=600)   # 10 min
# Split snapshot cache: successful pulls hold 30 min so we don't hammer Yahoo;
# negative cache (failed pulls) holds only 60 s so a transient 429 doesn't lock
# the ticker out for half an hour after Yahoo recovers.
_snapshot_cache: TTLCache = TTLCache(maxsize=300, ttl=1800)  # 30 min positive
# Two-tier negative cache: permanent (delisted/unknown) hold 24h so we don't
# keep paying the yfinance retry tax on the same dead symbol all day.
# Transient (rate-limit, network blip) hold 60s so we recover quickly.
_snapshot_neg_perm:     TTLCache = TTLCache(maxsize=500, ttl=yf_safe.NEG_TTL_PERMANENT_S)
_snapshot_neg_transient: TTLCache = TTLCache(maxsize=300, ttl=yf_safe.NEG_TTL_TRANSIENT_S)
_index_cache: TTLCache = TTLCache(maxsize=50, ttl=900)        # 15 min positive
_index_neg_perm:     TTLCache = TTLCache(maxsize=50, ttl=yf_safe.NEG_TTL_PERMANENT_S)
_index_neg_transient: TTLCache = TTLCache(maxsize=50, ttl=yf_safe.NEG_TTL_TRANSIENT_S)
_market_ctx_cache: TTLCache = TTLCache(maxsize=4, ttl=900)    # 15 min full market ctx
_news_query_cache: TTLCache = TTLCache(maxsize=40, ttl=1800)  # 30 min per news query
_earnings_cache: TTLCache = TTLCache(maxsize=300, ttl=43200)   # 12 h positive
_earnings_neg_perm:     TTLCache = TTLCache(maxsize=500, ttl=yf_safe.NEG_TTL_PERMANENT_S)
_earnings_neg_transient: TTLCache = TTLCache(maxsize=300, ttl=yf_safe.NEG_TTL_TRANSIENT_S)

# Thread pool for parallelizing per-holding enrichment in build_movers_context.
# 12 workers covers the typical 30-50 holding portfolio while staying gentle on
# yfinance rate limits (Yahoo gets cranky beyond ~20 concurrent connections).
from concurrent.futures import ThreadPoolExecutor as _Pool
_movers_pool = _Pool(max_workers=12, thread_name_prefix="movers-enrich")

# Lightweight cache for the price-only path (fast_info). Separate from
# _snapshot_cache so the heavy build_portfolio_context flow (which needs full
# fundamentals) and the light build_movers_context flow (which only needs
# price + change) don't fight over the same TTL.
_fast_snap_cache: TTLCache = TTLCache(maxsize=400, ttl=900)   # 15 min positive
_fast_snap_neg_perm:     TTLCache = TTLCache(maxsize=500, ttl=yf_safe.NEG_TTL_PERMANENT_S)
_fast_snap_neg_transient: TTLCache = TTLCache(maxsize=400, ttl=yf_safe.NEG_TTL_TRANSIENT_S)


def _fast_snapshot_inner(yf_symbol: str) -> dict | None:
    """Pure yfinance call inside yf_safe pool. Returns None when fast_info
    returned but had no usable data (signals delisted → permanent 24h cache).

    Critically does NOT catch exceptions: if fast_info access raises (rate
    limit, network, transient), let it propagate so yf_safe.classify_error
    can pattern-match the message and use a 60s transient TTL — NOT permanent.
    Earlier version swallowed the exception and poisoned 41 real tickers as
    permanent on a single mid-fanout Yahoo rate-limit blip."""
    fast = yf.Ticker(yf_symbol).fast_info
    price = float(fast.last_price) if hasattr(fast, "last_price") else None
    prev = float(fast.previous_close) if hasattr(fast, "previous_close") else None
    if price is None or prev is None or prev == 0:
        return None
    return {
        "current_price": round(price, 2),
        "change_percent": round((price - prev) / prev * 100, 2),
    }


def _fetch_fast_snapshot(ticker: str) -> dict:
    """fast_info-only snapshot — returns {current_price, change_percent}.
    Used by build_movers_context which doesn't need the full PE/ROE bundle.
    ~5-10× faster than _fetch_snapshot because it skips the slow .info JSON.

    Hardened: wrapped in yf_safe.run_with_timeout so a hanging Yahoo response
    or a delisted-symbol retry storm can't stall the calling worker thread
    for more than TIMEOUT_S (~4s). Permanent failures (delisted, unknown)
    cache for 24h so the same dead symbol doesn't keep paying the cost.
    Returns {} on failure; caller falls back to buy_price.
    """
    if ticker in _fast_snap_cache:
        return _fast_snap_cache[ticker]
    if ticker in _fast_snap_neg_perm or ticker in _fast_snap_neg_transient:
        return {}
    yf_symbol = resolve_yf_symbol(ticker)
    if not yf_symbol:
        _fast_snap_neg_perm[ticker] = True
        return {}

    # 6s budget: fast_info is normally <1s, but cold yfinance calls + the
    # occasional rate-limit retry can push it to 3-4s on healthy symbols.
    result, ok = yf_safe.run_with_timeout(_fast_snapshot_inner, yf_symbol, timeout_s=6.0)
    if not ok:
        # Timeout OR exception. result is None (timeout) or the exception.
        exc = result if isinstance(result, Exception) else None
        kind = yf_safe.classify_error(exc, None if exc is None else "__sentinel__")
        if kind == "permanent":
            _fast_snap_neg_perm[ticker] = True
        else:
            _fast_snap_neg_transient[ticker] = True
        if exc is not None:
            logger.debug("fast snapshot failed for %s: %s", ticker, exc)
        return {}
    if result is None:
        # Yahoo returned but with no data — almost always delisted/unknown.
        _fast_snap_neg_perm[ticker] = True
        return {}
    _fast_snap_cache[ticker] = result
    return result


# ---------------------------------------------------------------------------
# Sector → NIFTY sector-index symbol. Lets us compute excess return
# (stock_return − sector_return) so the LLM can distinguish idiosyncratic
# moves from sector-wide moves.
# ---------------------------------------------------------------------------
SECTOR_INDEX_MAP: dict[str, str] = {
    "Banking": "^NSEBANK",
    "Finance": "^NSEBANK",
    "Insurance": "^NSEBANK",
    "IT": "^CNXIT",
    "Automobiles": "^CNXAUTO",
    "Pharmaceuticals": "^CNXPHARMA",
    "FMCG": "^CNXFMCG",
    "Metals & Mining": "^CNXMETAL",
    "Oil & Gas": "^CNXENERGY",
    "Power": "^CNXENERGY",
    "Real Estate": "^CNXREALTY",
    "Infrastructure": "^CNXINFRA",
    "Cement": "^CNXINFRA",
    "Capital Goods": "^CNXINFRA",
    "Telecom": "^CNXMEDIA",
    "Consumer Durables": "^CNXFMCG",
}

# Global-news locales that drive overnight IN market direction.
_GLOBAL_SOURCES = [
    {"code": "US", "label": "United States", "query": "US economy stock market Federal Reserve Wall Street when:1d"},
    {"code": "CN", "label": "China",         "query": "China economy trade market finance when:1d"},
    {"code": "EU", "label": "Europe",        "query": "Europe economy ECB stock market finance when:1d"},
    {"code": "JP", "label": "Japan",         "query": "Japan economy Nikkei Bank of Japan finance when:1d"},
    {"code": "SA", "label": "Middle East",   "query": "Middle East oil OPEC crude when:1d"},
]


# ---------------------------------------------------------------------------
# Small, safe helpers
# ---------------------------------------------------------------------------
def _safe(val, digits=2):
    if val is None:
        return None
    try:
        return round(float(val), digits)
    except (ValueError, TypeError):
        return None


def _pct(val):
    if val is None:
        return None
    try:
        return round(float(val) * 100, 2)
    except (ValueError, TypeError):
        return None


def _percentile_rank(value: float | None, distribution: list[float]) -> int | None:
    """Return the percentile (0-100) of `value` within `distribution`. None-safe."""
    if value is None or not distribution:
        return None
    try:
        clean = [x for x in distribution if x is not None]
        if not clean:
            return None
        below = sum(1 for x in clean if x < value)
        return round(100 * below / len(clean))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Per-ticker yfinance snapshot (without hitting HTTP routes)
# ---------------------------------------------------------------------------
import time as _time


def _fetch_snapshot(ticker: str) -> dict:
    """Raw yfinance pull for one ticker. Returns {} on failure.

    Two-cache strategy: successful pulls hold 30 min (long enough that Yahoo's
    rate limit on Render's shared IPs doesn't keep biting). Failures cache for
    only 60 s so we retry promptly when Yahoo recovers, instead of returning
    empty data for half an hour.

    Single retry with 0.4 s backoff handles transient 429s.
    """
    if ticker in _snapshot_cache:
        return _snapshot_cache[ticker]
    if ticker in _snapshot_neg_perm or ticker in _snapshot_neg_transient:
        return {}
    yf_symbol = resolve_yf_symbol(ticker)
    if not yf_symbol:
        _snapshot_neg_perm[ticker] = True
        return {}

    def _inner() -> dict | None:
        t = yf.Ticker(yf_symbol)
        info = t.info or {}
        try:
            fast = t.fast_info
            price = float(fast.last_price) if hasattr(fast, "last_price") else 0.0
            prev = float(fast.previous_close) if hasattr(fast, "previous_close") else 0.0
            mcap = float(fast.market_cap) if hasattr(fast, "market_cap") and fast.market_cap else None
        except Exception:
            price, prev, mcap = 0.0, 0.0, None
        # Yahoo returns partial metadata for delisted symbols (name, exchange)
        # via quote_summary even when price data is gone. Don't trust `info`
        # being non-empty as a signal. The real test: did we get a price AND
        # at least one fundamental field? Otherwise treat as delisted.
        has_real_data = (
            price > 0 or info.get("trailingPE") is not None
            or info.get("returnOnEquity") is not None
            or info.get("marketCap") is not None
        )
        if not has_real_data:
            return None
        return {
            "current_price": _safe(price),
            "previous_close": _safe(prev),
            "change_percent": _safe(((price - prev) / prev * 100) if prev else 0),
            "market_cap": mcap,
            "pe_ratio": _safe(info.get("trailingPE")),
            "forward_pe": _safe(info.get("forwardPE")),
            "pb_ratio": _safe(info.get("priceToBook")),
            "ev_ebitda": _safe(info.get("enterpriseToEbitda")),
            "roe_pct": _pct(info.get("returnOnEquity")),
            "roa_pct": _pct(info.get("returnOnAssets")),
            "profit_margin_pct": _pct(info.get("profitMargins")),
            "operating_margin_pct": _pct(info.get("operatingMargins")),
            "revenue_growth_pct": _pct(info.get("revenueGrowth")),
            "earnings_growth_pct": _pct(info.get("earningsGrowth")),
            "debt_to_equity": _safe(info.get("debtToEquity")),
            "current_ratio": _safe(info.get("currentRatio")),
            "dividend_yield_pct": _pct(info.get("dividendYield")),
            "52w_high": _safe(info.get("fiftyTwoWeekHigh")),
            "52w_low": _safe(info.get("fiftyTwoWeekLow")),
            "business_summary": (info.get("longBusinessSummary") or "")[:400],
        }

    # 8s budget — heavier path (t.info hits Yahoo quote_summary which is slow
    # even for healthy symbols). Single attempt: the wall timeout + 24h
    # delisted cache + 30 min positive cache cover the cases that the old
    # 2-attempt + 0.4s sleep retry loop was protecting against.
    result, ok = yf_safe.run_with_timeout(_inner, timeout_s=8.0)
    if not ok:
        exc = result if isinstance(result, Exception) else None
        kind = yf_safe.classify_error(exc, None if exc is None else "__sentinel__")
        if kind == "permanent":
            _snapshot_neg_perm[ticker] = True
        else:
            _snapshot_neg_transient[ticker] = True
        if exc is not None:
            logger.warning("snapshot failed for %s: %s", ticker, exc)
        return {}
    if result is None:
        _snapshot_neg_perm[ticker] = True
        return {}
    _snapshot_cache[ticker] = result
    return result


# ---------------------------------------------------------------------------
# Peer benchmarking — Tickertape-style percentile scoring
# ---------------------------------------------------------------------------
_peer_cache: TTLCache = TTLCache(maxsize=50, ttl=1800)   # 30 min


def _peer_stats(sector: str, exclude_ticker: str) -> dict:
    """Compute sector-peer medians + the raw distribution for percentile ranking."""
    key = f"peer_{sector}"
    if key in _peer_cache:
        stats = dict(_peer_cache[key])
    else:
        peer_meta = [s for s in NSE_STOCKS if s["sector"] == sector][:10]
        collected: dict[str, list[float]] = {
            "pe_ratio": [], "pb_ratio": [], "roe_pct": [],
            "profit_margin_pct": [], "debt_to_equity": [], "revenue_growth_pct": [],
        }
        peers_data: list[dict] = []
        for pm in peer_meta:
            pt = pm["ticker"]
            snap = _fetch_snapshot(pt)
            peers_data.append({"ticker": pt, "name": pm.get("name", pt), "snapshot": snap})
            for k in collected:
                v = snap.get(k)
                if v is not None:
                    collected[k].append(float(v))
        stats = {
            "n_peers_sampled": len(peer_meta),
            "distributions": collected,
            "medians": {k: (round(statistics.median(v), 2) if v else None) for k, v in collected.items()},
            "peers": peers_data,
        }
        _peer_cache[key] = stats

    return stats


# ---------------------------------------------------------------------------
# Public compat helpers — deterministic scores + alternatives for UI
# ---------------------------------------------------------------------------
def compute_financial_scores(context: dict) -> dict:
    """
    Map peer percentiles to 0-100 UI scores. Deterministic — no LLM.
    Returns {revenue_growth_score, margin_score, debt_score, roe_score}.
    """
    ranks = (context.get("peer_benchmark") or {}).get("this_stock_percentile") or {}

    def _score(metric, invert=False):
        v = ranks.get(metric)
        if v is None:
            return None
        return int(100 - v) if invert else int(v)

    return {
        "revenue_growth_score": _score("revenue_growth_pct"),
        "margin_score": _score("profit_margin_pct"),
        "debt_score": _score("debt_to_equity", invert=True),  # lower D/E = better
        "roe_score": _score("roe_pct"),
    }


def get_sector_alternatives(context: dict, limit: int = 2) -> list[dict]:
    """
    Pick top same-sector peers by ROE (excluding this ticker, filtering out
    peers with worse ROE than current). Grounded — uses the peer sample
    already fetched for percentile ranking.
    """
    meta = context.get("meta") or {}
    sector = meta.get("sector")
    this_ticker = meta.get("ticker")
    this_snap = context.get("snapshot") or {}
    this_roe = this_snap.get("roe_pct")
    if not sector:
        return []

    peers = (_peer_cache.get(f"peer_{sector}") or {}).get("peers") or []
    ranked = []
    for p in peers:
        if p["ticker"] == this_ticker:
            continue
        snap = p.get("snapshot") or {}
        roe = snap.get("roe_pct")
        if roe is None:
            continue
        if this_roe is not None and roe <= this_roe:
            continue
        ranked.append({
            "ticker": p["ticker"],
            "name": p["name"],
            "roe_pct": roe,
            "profit_margin_pct": snap.get("profit_margin_pct"),
            "pe_ratio": snap.get("pe_ratio"),
        })

    ranked.sort(key=lambda x: x["roe_pct"], reverse=True)
    out = []
    for r in ranked[:limit]:
        why_bits = [f"ROE {r['roe_pct']}% (vs {this_ticker} {this_roe}%)" if this_roe is not None else f"ROE {r['roe_pct']}%"]
        if r.get("profit_margin_pct") is not None:
            why_bits.append(f"margin {r['profit_margin_pct']}%")
        out.append({
            "ticker": r["ticker"],
            "name": r["name"],
            "why": f"Same-sector peer with higher {', '.join(why_bits)}.",
            "edge": f"+{round(r['roe_pct'] - (this_roe or 0), 1)}pp ROE" if this_roe is not None else f"{r['roe_pct']}% ROE",
        })
    return out


# ---------------------------------------------------------------------------
# Public: single-stock context
# ---------------------------------------------------------------------------
def build_stock_context(ticker: str, include_news: bool = True, news_k: int = 5) -> dict:
    """
    Returns a structured dict that the LLM must ground its output in.

    Keys:
      meta            — ticker / name / sector
      snapshot        — live price + full ratios snapshot from yfinance
      peer_benchmark  — sector medians + percentile rank of this stock on key metrics
      signals         — rule-based strengths/concerns derived from ratios (Screener-style)
      news            — recent news articles (source, headline, snippet, date)
      generated_at    — iso timestamp for staleness checks
    """
    ticker = ticker.upper()
    cache_key = f"ctx_{ticker}_{int(include_news)}_{news_k}"
    if cache_key in _context_cache:
        return _context_cache[cache_key]

    meta = TICKER_TO_META.get(ticker, {"name": ticker, "sector": "Unknown"})
    snap = _fetch_snapshot(ticker)

    # --- peer benchmark + percentile rank on this stock ------------------
    peer = _peer_stats(meta.get("sector", "Unknown"), ticker)
    ranks: dict[str, int | None] = {}
    for k, dist in peer.get("distributions", {}).items():
        ranks[k] = _percentile_rank(snap.get(k), dist)

    # --- rule-based signals (Screener-style pros/cons from raw numbers) --
    signals = _derive_signals(snap, peer.get("medians", {}))

    # --- news -----------------------------------------------------------
    news: list[dict] = []
    if include_news:
        try:
            raw_news = data_ingestion.retrieve_context(ticker, top_k=news_k)
            for i, n in enumerate(raw_news):
                news.append({
                    "id": f"news[{i}]",
                    "source": n.get("source"),
                    "headline": n.get("headline"),
                    "snippet": (n.get("snippet") or "")[:300],
                    "published_date": n.get("published_date"),
                })
        except Exception as e:
            logger.warning("news fetch failed for %s: %s", ticker, e)

    from datetime import datetime
    ctx = {
        "meta": {"ticker": ticker, "name": meta.get("name"), "sector": meta.get("sector")},
        "snapshot": snap,
        "peer_benchmark": {
            "sector": meta.get("sector"),
            "n_peers_sampled": peer.get("n_peers_sampled", 0),
            "medians": peer.get("medians", {}),
            "this_stock_percentile": ranks,  # 0=worst, 100=best within sample
        },
        "signals": signals,
        "news": news,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
    _context_cache[cache_key] = ctx
    return ctx


def _derive_signals(snap: dict, medians: dict) -> dict:
    """Rule-based strengths/concerns. Each entry carries its own provenance."""
    strengths: list[dict] = []
    concerns: list[dict] = []

    def _add(bucket, text, source):
        bucket.append({"text": text, "source": source})

    roe = snap.get("roe_pct")
    if roe is not None:
        if roe >= 18:
            _add(strengths, f"ROE of {roe}% indicates strong return on shareholder capital.", "snapshot.roe_pct")
        elif roe < 8:
            _add(concerns, f"Low ROE of {roe}% suggests weak capital efficiency.", "snapshot.roe_pct")

    de = snap.get("debt_to_equity")
    if de is not None:
        if de > 150:
            _add(concerns, f"Debt-to-equity of {de} is elevated; balance-sheet risk.", "snapshot.debt_to_equity")
        elif de < 30:
            _add(strengths, f"Low debt-to-equity ({de}) — conservative balance sheet.", "snapshot.debt_to_equity")

    pe = snap.get("pe_ratio")
    med_pe = medians.get("pe_ratio")
    if pe is not None and med_pe:
        if pe > med_pe * 1.3:
            _add(concerns, f"P/E of {pe} is ~{round((pe/med_pe-1)*100)}% above sector median ({med_pe}).",
                 "peer_benchmark.medians.pe_ratio")
        elif pe < med_pe * 0.7:
            _add(strengths, f"P/E of {pe} is ~{round((1-pe/med_pe)*100)}% below sector median ({med_pe}).",
                 "peer_benchmark.medians.pe_ratio")

    rev_g = snap.get("revenue_growth_pct")
    if rev_g is not None:
        if rev_g > 15:
            _add(strengths, f"Revenue growth of {rev_g}% YoY is strong.", "snapshot.revenue_growth_pct")
        elif rev_g < 0:
            _add(concerns, f"Revenue is contracting ({rev_g}% YoY).", "snapshot.revenue_growth_pct")

    margin = snap.get("profit_margin_pct")
    if margin is not None:
        if margin < 0:
            _add(concerns, f"Company is loss-making (profit margin {margin}%).", "snapshot.profit_margin_pct")
        elif margin > 20:
            _add(strengths, f"Profit margin of {margin}% is healthy.", "snapshot.profit_margin_pct")

    # 52-week position
    price = snap.get("current_price")
    hi, lo = snap.get("52w_high"), snap.get("52w_low")
    if price and hi and lo and hi > lo:
        band = round((price - lo) / (hi - lo) * 100)
        if band >= 85:
            _add(concerns, f"Trading near 52-week high ({band}% of range) — entry-price risk.",
                 "snapshot.52w_high")
        elif band <= 15:
            _add(strengths, f"Trading near 52-week low ({band}% of range) — potential value entry.",
                 "snapshot.52w_low")

    return {"strengths": strengths, "concerns": concerns}


# ---------------------------------------------------------------------------
# Portfolio context
# ---------------------------------------------------------------------------
def build_portfolio_context(holdings: list[dict]) -> dict:
    """
    holdings: list of {ticker, quantity, buy_price}. Builds an aggregate context:
      - per-holding snapshot + P&L + sector
      - portfolio-level sector allocation
      - concentration metrics (top-holding %, top-sector %)
      - per-holding rule-based signals (abbreviated)
    """
    if not holdings:
        return {"holdings": [], "aggregate": {}, "generated_at": None}

    enriched: list[dict] = []
    total_value = 0.0
    sector_value: dict[str, float] = {}
    for h in holdings:
        t = h["ticker"].upper()
        meta = TICKER_TO_META.get(t, {"name": t, "sector": "Unknown"})
        snap = _fetch_snapshot(t)
        price = snap.get("current_price") or h.get("buy_price") or 0.0
        qty = float(h.get("quantity", 0))
        buy = float(h.get("buy_price", 0))
        value = price * qty
        total_value += value
        sector_value[meta["sector"]] = sector_value.get(meta["sector"], 0.0) + value
        pnl_pct = ((price - buy) / buy * 100) if buy else 0.0
        enriched.append({
            "ticker": t,
            "name": meta["name"],
            "sector": meta["sector"],
            "quantity": qty,
            "buy_price": buy,
            "current_price": price,
            "position_value": round(value, 2),
            "unrealized_pnl_pct": round(pnl_pct, 2),
            "snapshot": snap,
        })

    # Allocations + concentration
    allocations = []
    for t in enriched:
        if total_value > 0:
            t["weight_pct"] = round(t["position_value"] / total_value * 100, 2)
            allocations.append({"ticker": t["ticker"], "weight_pct": t["weight_pct"]})
        else:
            t["weight_pct"] = 0.0
            allocations.append({"ticker": t["ticker"], "weight_pct": 0.0})

    sector_alloc = [
        {"sector": s, "weight_pct": round(v / total_value * 100, 2) if total_value else 0.0}
        for s, v in sector_value.items()
    ]
    sector_alloc.sort(key=lambda x: x["weight_pct"], reverse=True)

    top_holding = max(allocations, key=lambda a: a["weight_pct"]) if allocations else {}
    top_sector = sector_alloc[0] if sector_alloc else {}

    from datetime import datetime
    return {
        "holdings": enriched,
        "aggregate": {
            "total_value": round(total_value, 2),
            "n_holdings": len(enriched),
            "sector_allocation": sector_alloc,
            "top_holding_pct": top_holding.get("weight_pct"),
            "top_sector_pct": top_sector.get("weight_pct"),
            "top_sector": top_sector.get("sector"),
            "concentration_flag": (top_holding.get("weight_pct", 0) or 0) > 35
                                  or (top_sector.get("weight_pct", 0) or 0) > 50,
        },
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# Context Engine — market & movers
# ---------------------------------------------------------------------------
def _fetch_index_change(symbol: str) -> dict | None:
    """Today's % change for a yfinance index symbol.

    Successful pulls cache 15 min; failures cache only 60 s so a transient 429
    doesn't lock the index out for the rest of the trading day. One retry with
    short backoff handles intermittent rate limiting.
    """
    if symbol in _index_cache:
        return _index_cache[symbol]
    if symbol in _index_neg_perm or symbol in _index_neg_transient:
        return None

    def _inner() -> dict | None:
        tk = yf.Ticker(symbol)
        price = prev = 0.0
        try:
            fi = tk.fast_info
            price = float(getattr(fi, "last_price", 0) or 0)
            prev = float(getattr(fi, "previous_close", 0) or 0)
        except Exception:
            pass
        if not price:
            hist = tk.history(period="5d")
            if hist is not None and not hist.empty:
                price = float(hist["Close"].iloc[-1])
                prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else price
        if not price:
            return None
        change_pct = round(((price - prev) / prev * 100) if prev else 0.0, 2)
        return {"symbol": symbol, "value": round(price, 2), "change_percent": change_pct}

    # 5s budget — index symbols are usually fast (fast_info is enough), but
    # the history fallback can be slow if Yahoo is rate-limiting.
    result, ok = yf_safe.run_with_timeout(_inner, timeout_s=5.0)
    if not ok:
        exc = result if isinstance(result, Exception) else None
        kind = yf_safe.classify_error(exc, None if exc is None else "__sentinel__")
        if kind == "permanent":
            _index_neg_perm[symbol] = True
        else:
            _index_neg_transient[symbol] = True
        if exc is not None:
            logger.warning("index fetch failed for %s: %s", symbol, exc)
        return None
    if result is None:
        _index_neg_perm[symbol] = True
        return None
    _index_cache[symbol] = result
    return result


def _fetch_rss_headlines(query: str, hl: str = "en-IN", gl: str = "IN",
                        ceid: str = "IN:en", n: int = 6) -> list[dict]:
    """Lightweight Google News RSS fetcher with locale params. 15-min cache.

    Uses requests.get with a hard timeout — feedparser.parse(url) has no
    timeout of its own and on a slow Google News response it would hang the
    whole Context Engine SSE stream.
    """
    key = f"{query}|{hl}|{gl}|{ceid}"
    if key in _news_query_cache:
        return _news_query_cache[key][:n]
    try:
        url = (f"https://news.google.com/rss/search?q={quote(query)}"
               f"&hl={hl}&gl={gl}&ceid={ceid}")
        import requests as _rq
        r = _rq.get(url, timeout=6.0,
                    headers={"User-Agent": "FinContext/1.0"})
        r.raise_for_status()
        feed = feedparser.parse(r.content)
        out = []
        for entry in feed.entries[:n]:
            parts = entry.title.rsplit(" - ", 1)
            headline = parts[0].strip()
            source = parts[1].strip() if len(parts) > 1 else "Google News"
            snippet = ""
            if hasattr(entry, "summary"):
                snippet = re.sub(r"<[^>]+>", "", entry.summary).strip()[:240]
            out.append({
                "source": source,
                "headline": headline,
                "snippet": snippet or headline,
            })
        _news_query_cache[key] = out
        return out
    except Exception as e:
        logger.warning("rss fetch failed for '%s': %s", query, e)
        return []


def build_market_context() -> dict:
    """
    Today's market snapshot shared by today-attribution and tomorrow-outlook.
    Cached 10 min so repeated calls in one render are cheap.

    Returns:
      indices         — NIFTY 50 + NIFTY Midcap 100 today
      sectors         — per-sector index returns today
      india_headlines — today's top IN macro headlines, indexed as india_news[i]
      global_headlines— today's top headlines from US/CN/EU/JP/SA, indexed as global_news[i]
    """
    if "market_ctx" in _market_ctx_cache:
        return _market_ctx_cache["market_ctx"]

    indices: dict[str, dict | None] = {
        "nifty_50": _fetch_index_change("^NSEI"),
        "nifty_midcap_100": _fetch_index_change("NIFTY_MIDCAP_100.NS"),
        "sensex": _fetch_index_change("^BSESN"),
    }

    sectors: list[dict] = []
    seen: set[str] = set()
    for sector_name, sym in SECTOR_INDEX_MAP.items():
        if sym in seen:
            continue
        seen.add(sym)
        data = _fetch_index_change(sym)
        if data:
            sectors.append({"sector": sector_name, "index": sym, **data})

    # India headlines — multi-source pool (Moneycontrol, ET, Mint, BS, Hindu
    # BusinessLine) + Google News. Earlier this was a single Google query which
    # returned the same 5 articles for hours because Google's ranking is stable
    # — UI felt stuck on yesterday's news. The pool gives genuine variety; we
    # take 6 from the pool and 3 from Google as supplement, dedup, and freshness-
    # sort. Per-source failures are isolated inside news_sources.
    india_pool = news_sources.fetch_india_market_pool(n=12)
    india_query = "India economy stock market finance when:1d"
    india_google = news_sources.google_news_for_query(
        india_query, hl="en-IN", gl="IN", ceid="IN:en", n=6
    )
    india_merged = news_sources.dedup_items(india_pool + india_google)
    # Keep the top 10 — more variety than the old 6 since we have real source diversity now.
    india_news = [
        {"id": f"india_news[{i}]", **n} for i, n in enumerate(india_merged[:10])
    ]

    # Policy + regulatory pulse (PIB government press releases + RBI). This is
    # the Indian-wedge data global tools don't surface. Items carry sector tags
    # (banking, auto, defence, ...) so the LLM annotator can map them onto the
    # user's holdings even when the headline names no specific company.
    policy_items_raw: list[dict] = []
    try:
        policy_items_raw = policy_feeds.fetch_all_policy_items(limit_per_source=15)
    except Exception as e:
        logger.warning("policy feed fetch failed: %s", e)
    policy_items = [
        {"id": f"policy_news[{i}]", **n} for i, n in enumerate(policy_items_raw)
    ]

    global_news: list[dict] = []
    idx = 0
    for src in _GLOBAL_SOURCES:
        items = _fetch_rss_headlines(
            src["query"], hl="en-US", gl="US", ceid="US:en", n=3
        )
        for n in items:
            global_news.append({
                "id": f"global_news[{idx}]",
                "country": src["code"],
                "country_label": src["label"],
                **n,
            })
            idx += 1

    # FII/DII daily flows (moneycontrol). Best-effort — None if scrape fails.
    flows = None
    try:
        flows = market_flows.fetch_latest_flows()
    except Exception as e:
        logger.warning("market_flows fetch failed: %s", e)

    from datetime import datetime
    ctx = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "indices": indices,
        "sectors": sectors,
        "flows": flows,
        "india_headlines": india_news,
        "global_headlines": global_news,
        "policy_headlines": policy_items,
    }
    _market_ctx_cache["market_ctx"] = ctx
    return ctx


def _upcoming_earnings(ticker: str, max_days: int = 14) -> dict | None:
    """Return {date: ISO, days_ahead: int} for the next earnings inside `max_days`,
    or None if none / unknown / yfinance is flaky. Cached 12 h positive / 5 min negative.

    yfinance ships earnings via `Ticker.calendar` (a dict in 0.2.x) and a fallback
    DataFrame from `get_earnings_dates`. We try both because the shape varies by
    yfinance version and by ticker — Indian tickers in particular often return only
    one of the two.
    """
    if ticker in _earnings_cache:
        return _earnings_cache[ticker]
    if ticker in _earnings_neg_perm or ticker in _earnings_neg_transient:
        return None
    yf_symbol = resolve_yf_symbol(ticker)
    if not yf_symbol:
        _earnings_neg_perm[ticker] = True
        return None

    from datetime import datetime, timezone, date

    today = datetime.now(timezone.utc).date()

    def _inner() -> date | None:
        ed: date | None = None
        tk = yf.Ticker(yf_symbol)
        cal = getattr(tk, "calendar", None)
        if isinstance(cal, dict):
            v = cal.get("Earnings Date") or cal.get("earnings_date")
            if v:
                cand = v[0] if isinstance(v, list) and v else v
                if hasattr(cand, "date"):
                    cand = cand.date()
                if isinstance(cand, date):
                    ed = cand
        if ed is None:
            try:
                df = tk.get_earnings_dates(limit=4)
                if df is not None and not df.empty:
                    for ts in df.index:
                        d = ts.date() if hasattr(ts, "date") else None
                        if d and d >= today:
                            ed = d
                            break
            except Exception:
                pass
        return ed

    # 5s budget — earnings_dates endpoint can be slow for some tickers.
    result, ok = yf_safe.run_with_timeout(_inner, timeout_s=5.0)
    if not ok:
        exc = result if isinstance(result, Exception) else None
        kind = yf_safe.classify_error(exc, None if exc is None else "__sentinel__")
        if kind == "permanent":
            _earnings_neg_perm[ticker] = True
        else:
            _earnings_neg_transient[ticker] = True
        if exc is not None:
            logger.debug("earnings lookup failed for %s: %s", ticker, exc)
        return None
    ed = result
    if ed is None:
        # No exception, just no scheduled earnings — treat as "permanent for
        # today" (12h positive miss equivalent). The 24h cache is fine because
        # earnings dates don't pop in mid-day.
        _earnings_neg_perm[ticker] = True
        return None
    delta = (ed - today).days
    if delta < 0 or delta > max_days:
        _earnings_neg_perm[ticker] = True
        return None
    out = {"date": ed.isoformat(), "days_ahead": delta}
    _earnings_cache[ticker] = out
    return out


def compute_portfolio_health(context: dict) -> dict:
    """Deterministic per-axis portfolio-health scores (0-100) computed from the
    grounding context. Run alongside the LLM so the AI Analysis tab never shows
    empty bars when the LLM degrades, times out, or returns nulls.

    Returns: {diversification, quality, risk, momentum} — None for any axis
    whose input data is too sparse.

      • diversification — penalizes single-holding and single-sector concentration
      • quality         — bucketed score over ROE / profit margin / debt-to-equity,
                          weighted by position size
      • risk            — inverse risk (higher = safer): concentration penalty
                          + holding-count bonus
      • momentum        — weighted 20-day return across holdings, mapped to 0-100

    Caller is expected to merge: prefer the LLM's value, fall back to these.
    """
    aggregate = context.get("aggregate") or {}
    holdings = context.get("holdings") or []

    # --- Diversification ---
    div = None
    if aggregate:
        top_h = aggregate.get("top_holding_pct") or 0
        top_s = aggregate.get("top_sector_pct") or 0
        sector_count = len(aggregate.get("sector_allocation") or [])
        n = aggregate.get("n_holdings") or len(holdings)
        score = 100
        if top_h > 20:           score -= (top_h - 20) * 1.4
        if top_s > 35:           score -= (top_s - 35) * 1.0
        if sector_count < 4:     score -= (4 - sector_count) * 8
        if n < 8:                score -= (8 - n) * 3
        div = max(0, min(100, round(score)))

    # --- Quality ---
    def _bucket_roe(v):
        if v is None: return None
        if v < 0:  return 5
        if v < 8:  return 30
        if v < 14: return 55
        if v < 20: return 75
        return 90

    def _bucket_margin(v):
        if v is None: return None
        if v < 0:  return 5
        if v < 5:  return 30
        if v < 10: return 55
        if v < 20: return 75
        return 90

    def _bucket_de(v):
        if v is None: return None
        # yfinance debt_to_equity is sometimes in percent (e.g. 120 = 1.2x).
        # Normalise heuristically: anything > 5 is almost certainly a percent.
        d = v / 100.0 if v > 5 else v
        if d > 2:    return 15
        if d > 1:    return 40
        if d > 0.5:  return 65
        return 85

    quality_pairs: list[tuple[float, float]] = []
    for h in holdings:
        snap = h.get("snapshot") or {}
        per = [b for b in (
            _bucket_roe(snap.get("roe_pct")),
            _bucket_margin(snap.get("profit_margin_pct")),
            _bucket_de(snap.get("debt_to_equity")),
        ) if b is not None]
        if per:
            w = h.get("weight_pct") or 0
            quality_pairs.append((sum(per) / len(per), w))
    qty = None
    if quality_pairs:
        num = sum(s * w for s, w in quality_pairs)
        den = sum(w for _, w in quality_pairs)
        qty = round(num / den) if den > 0 else round(sum(s for s, _ in quality_pairs) / len(quality_pairs))

    # --- Risk (inverse: high = safer) ---
    risk = None
    if aggregate:
        score = 100
        top_h = aggregate.get("top_holding_pct") or 0
        top_s = aggregate.get("top_sector_pct") or 0
        if aggregate.get("concentration_flag"):  score -= 25
        if top_h > 25:                            score -= (top_h - 25) * 1.5
        if top_s > 40:                            score -= (top_s - 40) * 0.8
        # Penalize unrealized-loss tilt: average unrealized P&L < 0 is risky.
        pnls = [h.get("unrealized_pnl_pct") for h in holdings if h.get("unrealized_pnl_pct") is not None]
        if pnls:
            avg_pnl = sum(pnls) / len(pnls)
            if avg_pnl < -10: score -= 10
            elif avg_pnl < -5: score -= 5
        risk = max(0, min(100, round(score)))

    # --- Momentum — weighted 20d return, mapped to 0-100 ---
    mom = None
    mom_pairs: list[tuple[float, float]] = []
    for h in holdings:
        t = (h.get("ticker") or "").upper()
        sig = technicals.compute_signals(t) if t else None
        if sig and sig.get("momentum_20d_pct") is not None:
            w = h.get("weight_pct") or 0
            mom_pairs.append((sig["momentum_20d_pct"], w))
    if mom_pairs:
        wnum = sum(m * w for m, w in mom_pairs)
        wden = sum(w for _, w in mom_pairs)
        if wden > 0:
            avg = wnum / wden
            # [-20, +20] → [0, 100] linear; clipped.
            mom = max(0, min(100, round(50 + avg * 2.5)))

    return {
        "diversification": div,
        "quality": qty,
        "risk": risk,
        "momentum": mom,
    }


def build_movers_context(holdings: list[dict], market_ctx: dict | None = None) -> dict:
    """
    Per-holding "move today" context: change_percent + sector index return +
    excess return + ticker-level news. Plus portfolio aggregate returns.

    holdings: [{ticker, quantity, buy_price}]
    """
    if market_ctx is None:
        market_ctx = build_market_context()

    sector_returns = {s["sector"]: s["change_percent"] for s in market_ctx.get("sectors", [])}
    holdings_ctx: list[dict] = []
    total_value = 0.0
    weighted_change = 0.0

    # Batch pgvector semantic match across ALL tickers at once — far cheaper
    # than one RPC per ticker. Returns annotated news with `affected_ticker`.
    semantic_by_ticker: dict[str, list[dict]] = {}
    try:
        all_tickers = [
            (h.get("ticker") or "").upper() for h in (holdings or []) if h.get("ticker")
        ]
        if all_tickers and vector_store.is_available():
            matches = vector_store.match_news_for_tickers(
                tickers=all_tickers,
                match_count=max(20, len(all_tickers) * 3),
                recency_hours=36,
                match_threshold=0.55,
            )
            for m in matches:
                aff = (m.get("affected_ticker") or "").upper()
                if not aff:
                    continue
                semantic_by_ticker.setdefault(aff, []).append(m)
    except Exception as e:
        logger.warning("semantic match failed in movers context: %s", e)

    # ---- Parallel per-holding enrichment ------------------------------------
    # Each holding needs ~4 sync calls (snapshot, RSS news, technicals, earnings)
    # that are individually 100-500ms. Sequentially that's 25-40s for a 41-stock
    # portfolio; in 12 threads it drops to ~3-5s. Heavy yfinance functions are
    # I/O-bound (HTTPS to Yahoo) so threading gives near-linear speedup despite
    # the GIL. Caches are mostly idempotent under concurrent writes.
    def _enrich_one(h: dict) -> dict | None:
        t = (h.get("ticker") or "").upper()
        if not t:
            return None
        meta = TICKER_TO_META.get(t, {"name": t, "sector": "Unknown"})
        # Light snapshot — only price + change (we don't need PE/ROE here).
        # Skips the slow t.info call → 5-10× faster cold path.
        snap = _fetch_fast_snapshot(t)
        price = snap.get("current_price") or h.get("buy_price") or 0.0
        qty = float(h.get("quantity") or 0)
        value = price * qty
        change = snap.get("change_percent")
        sector = meta.get("sector", "Unknown")
        sector_return = sector_returns.get(sector)
        excess = None
        if change is not None and sector_return is not None:
            excess = round(change - sector_return, 2)

        # Keyword news (RSS)
        news_items: list[dict] = []
        try:
            raw = data_ingestion.retrieve_context(t, top_k=3)
            for i, n in enumerate(raw):
                news_items.append({
                    "id": f"{t}_news[{i}]",
                    "source": n.get("source"),
                    "headline": n.get("headline"),
                    "snippet": (n.get("snippet") or "")[:200],
                })
        except Exception as e:
            logger.warning("news fetch failed in movers for %s: %s", t, e)

        # Semantic news from the pre-fetched batch (cheap dict lookup).
        sem_items = [
            {
                "id": f"{t}_sem[{i}]",
                "source": m.get("source"),
                "headline": m.get("headline"),
                "similarity": round(float(m.get("similarity") or 0), 3),
            }
            for i, m in enumerate((semantic_by_ticker.get(t) or [])[:3])
        ]

        tech = technicals.compute_signals(t)
        earnings = _upcoming_earnings(t, max_days=14)

        return {
            "ticker": t,
            "name": meta.get("name"),
            "sector": sector,
            "current_price": _safe(price),
            "position_value": round(value, 2),
            "change_percent_today": change,
            "sector_index_return_today": sector_return,
            "excess_return_today": excess,
            "news": news_items,
            "semantic_news": sem_items,
            "technicals": tech,
            "upcoming_earnings": earnings,
            # Stash for the aggregator below.
            "_value_for_total": value,
            "_change_for_weighted": change,
        }

    # Submit all and wait — preserve input order via .map().
    results = list(_movers_pool.map(_enrich_one, holdings or []))
    for r in results:
        if r is None:
            continue
        # Pull aggregator fields out of the per-holding dict before storing.
        v = r.pop("_value_for_total", 0.0)
        c = r.pop("_change_for_weighted", None)
        total_value += v
        if c is not None:
            weighted_change += c * v
        holdings_ctx.append(r)

    # Portfolio-level return today (value-weighted)
    portfolio_return = round(weighted_change / total_value, 2) if total_value else None

    # Classify movers so the LLM has an easy hook
    def _mover_bucket(h):
        c = h.get("change_percent_today")
        if c is None:
            return "flat"
        if c >= 1.5:
            return "strong_gainer"
        if c <= -1.5:
            return "strong_loser"
        return "flat"

    for h in holdings_ctx:
        h["mover_bucket"] = _mover_bucket(h)

    from datetime import datetime
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "portfolio_return_today_pct": portfolio_return,
        "holdings": holdings_ctx,
        "market": {
            "indices": market_ctx.get("indices", {}),
            "sectors": market_ctx.get("sectors", []),
            "flows": market_ctx.get("flows"),
        },
    }


# ---------------------------------------------------------------------------
# Morning Brief — personalized "what matters for YOUR portfolio today"
# ---------------------------------------------------------------------------
def build_morning_brief_context(
    holdings: list[dict] | None,
    watchlist_tickers: list[str] | None,
) -> dict:
    """
    Build a slim CONTEXT for the morning brief LLM call.
    Combines:
      - market snapshot (indices, sectors, India + global headlines)
      - per-ticker headlines for current portfolio holdings (max 2 each)
      - per-ticker headlines for watchlist tickers not already in holdings (max 1 each)
      - sector exposure summary so the LLM can flag sector-level catalysts

    Holdings format: [{ticker, quantity, buy_price}].
    Watchlist tickers: bare list of symbols.

    Token-conscious: snippets dropped for ticker news, only headline + source kept.
    Total context typically <4K tokens — fits Groq free tier comfortably.
    """
    market_ctx = build_market_context()

    holdings = holdings or []
    watchlist_tickers = watchlist_tickers or []

    held_tickers = [(h.get("ticker") or "").upper() for h in holdings if h.get("ticker")]
    held_set = set(held_tickers)
    watch_only = [t.upper() for t in watchlist_tickers if t and t.upper() not in held_set]

    # Sector exposure (rough — based on buy_price * quantity since we don't fetch live prices here)
    sector_exposure: dict[str, float] = {}
    total_invested = 0.0
    for h in holdings:
        t = (h.get("ticker") or "").upper()
        if not t:
            continue
        meta = TICKER_TO_META.get(t, {"sector": "Unknown"})
        invested = float(h.get("quantity") or 0) * float(h.get("buy_price") or 0)
        sector_exposure[meta.get("sector", "Unknown")] = (
            sector_exposure.get(meta.get("sector", "Unknown"), 0.0) + invested
        )
        total_invested += invested

    sector_exposure_pct = (
        [
            {"sector": s, "weight_pct": round(v / total_invested * 100, 1)}
            for s, v in sorted(sector_exposure.items(), key=lambda x: -x[1])
        ]
        if total_invested
        else []
    )

    holdings_summary: list[dict] = []
    for h in holdings:
        t = (h.get("ticker") or "").upper()
        if not t:
            continue
        meta = TICKER_TO_META.get(t, {"name": t, "sector": "Unknown"})
        news_items: list[dict] = []
        try:
            raw = data_ingestion.retrieve_context(t, top_k=2)
            for i, n in enumerate(raw):
                news_items.append({
                    "id": f"{t}_news[{i}]",
                    "source": n.get("source"),
                    "headline": n.get("headline"),
                })
        except Exception as e:
            logger.warning("morning brief: news fetch failed for %s: %s", t, e)
        # Upcoming earnings (≤14 days). Without this the LLM has no concrete
        # event to cite for `watch_today` / `tomorrow_setup` and falls back to
        # filler — "investors should keep an eye on upcoming data releases".
        earnings = _upcoming_earnings(t, max_days=14)
        holdings_summary.append({
            "ticker": t,
            "name": meta.get("name"),
            "sector": meta.get("sector"),
            "news": news_items,
            "upcoming_earnings": earnings,
        })

    watchlist_summary: list[dict] = []
    for t in watch_only[:8]:  # cap so context stays small
        meta = TICKER_TO_META.get(t, {"name": t, "sector": "Unknown"})
        news_items: list[dict] = []
        try:
            raw = data_ingestion.retrieve_context(t, top_k=1)
            for i, n in enumerate(raw):
                news_items.append({
                    "id": f"{t}_news[{i}]",
                    "source": n.get("source"),
                    "headline": n.get("headline"),
                })
        except Exception as e:
            logger.warning("morning brief: news fetch failed for watch %s: %s", t, e)
        earnings = _upcoming_earnings(t, max_days=14)
        watchlist_summary.append({
            "ticker": t,
            "name": meta.get("name"),
            "sector": meta.get("sector"),
            "news": news_items,
            "upcoming_earnings": earnings,
        })

    from datetime import datetime
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "user_universe": {
            "holdings_count": len(holdings_summary),
            "watchlist_count": len(watchlist_summary),
            "sector_exposure_pct": sector_exposure_pct,
        },
        "indices": market_ctx.get("indices", {}),
        "sectors": market_ctx.get("sectors", []),
        "india_headlines": market_ctx.get("india_headlines", []),
        "global_headlines": market_ctx.get("global_headlines", []),
        "policy_headlines": market_ctx.get("policy_headlines", []),
        "holdings": holdings_summary,
        "watchlist": watchlist_summary,
    }
