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
"""

from __future__ import annotations

import logging
import statistics
from typing import Any

import yfinance as yf
from cachetools import TTLCache

from app.nse_universe import TICKER_TO_META, TICKER_TO_YF, NSE_STOCKS
from app.services import data_ingestion

logger = logging.getLogger(__name__)

_context_cache: TTLCache = TTLCache(maxsize=200, ttl=600)   # 10 min
_snapshot_cache: TTLCache = TTLCache(maxsize=300, ttl=600)  # 10 min per-ticker snapshot


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
def _fetch_snapshot(ticker: str) -> dict:
    """Raw yfinance pull for one ticker. Returns {} on failure."""
    if ticker in _snapshot_cache:
        return _snapshot_cache[ticker]
    yf_symbol = TICKER_TO_YF.get(ticker)
    if not yf_symbol:
        _snapshot_cache[ticker] = {}
        return {}
    try:
        t = yf.Ticker(yf_symbol)
        info = t.info or {}
        try:
            fast = t.fast_info
            price = float(fast.last_price) if hasattr(fast, "last_price") else 0.0
            prev = float(fast.previous_close) if hasattr(fast, "previous_close") else 0.0
            mcap = float(fast.market_cap) if hasattr(fast, "market_cap") and fast.market_cap else None
        except Exception:
            price, prev, mcap = 0.0, 0.0, None

        snap = {
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
        _snapshot_cache[ticker] = snap
        return snap
    except Exception as e:
        logger.warning("snapshot failed for %s: %s", ticker, e)
        _snapshot_cache[ticker] = {}
        return {}


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
