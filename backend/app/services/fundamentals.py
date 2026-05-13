"""
Fundamentals service
====================
Pure data layer for company fundamentals (yfinance-backed).

Why this exists: previously routers/company_data.py mixed HTTP routing with
yfinance fetching, formatting helpers, and ad-hoc caches. Other modules that
needed the same data (e.g. grounding.py, future deep-dive synthesis) had no
way to call into it without going through HTTP. Pulling the I/O down into a
service lets routers stay thin and prevents duplicate fetch/format logic.

Public surface:
- get_overview(ticker)      -> dict
- get_financials(ticker, period) -> dict
- get_ratios(ticker)        -> dict
- get_peers(ticker)         -> dict
- get_shareholding(ticker)  -> dict

All functions raise LookupError for unknown tickers; the router maps that to
HTTP 404.
"""

from __future__ import annotations

import logging
import yfinance as yf

from app.nse_universe import TICKER_TO_YF, TICKER_TO_META, NSE_STOCKS, resolve_yf_symbol
from app.services.cache import make_named_cache

logger = logging.getLogger(__name__)

_overview_cache = make_named_cache("overview", maxsize=200)
_financials_cache = make_named_cache("financials", maxsize=100)
_ratios_cache = make_named_cache("ratios", maxsize=200)
_holders_cache = make_named_cache("shareholding", maxsize=100)
_peers_cache = make_named_cache("fundamentals", maxsize=100)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------
def _resolve_ticker(ticker: str) -> tuple[yf.Ticker, str, str]:
    """Resolve an internal ticker to a yfinance Ticker. Falls back to
    `{TICKER}.NS` for tickers outside our curated universe so users with
    long-tail NSE holdings still get fundamentals."""
    ticker = ticker.upper()
    yf_symbol = resolve_yf_symbol(ticker)
    if not yf_symbol:
        raise LookupError(f"Ticker '{ticker}' could not be resolved")
    return yf.Ticker(yf_symbol), ticker, yf_symbol


def _safe_round(val, digits: int = 2) -> float | None:
    if val is None:
        return None
    try:
        return round(float(val), digits)
    except (ValueError, TypeError):
        return None


def _pct(val) -> float | None:
    """Convert decimal ratio to percentage."""
    if val is None:
        return None
    try:
        return round(float(val) * 100, 2)
    except (ValueError, TypeError):
        return None


def _fmt_cr(val) -> str:
    """Format absolute value as ₹Cr / ₹K Cr / ₹L Cr."""
    if val is None:
        return "—"
    try:
        v = float(val)
        cr = v / 1e7
        if cr >= 100000:
            return f"₹{cr/100000:.2f}L Cr"
        if cr >= 1000:
            return f"₹{cr/1000:.2f}K Cr"
        return f"₹{cr:.0f} Cr"
    except (ValueError, TypeError):
        return "—"


def _df_to_dict(df) -> dict:
    """Convert a yfinance financial-statement DataFrame to a JSON-friendly dict."""
    if df is None or df.empty:
        return {}
    result: dict = {}
    for col in df.columns:
        col_label = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)
        col_data: dict = {}
        for idx, val in df[col].items():
            row_label = str(idx)
            try:
                if val is not None and str(val) != "nan":
                    col_data[row_label] = round(float(val), 0)
                else:
                    col_data[row_label] = None
            except (ValueError, TypeError):
                col_data[row_label] = None
        result[col_label] = col_data
    return result


def _quote_from_fast_info(yf_obj: yf.Ticker) -> tuple[float, float, float | None]:
    """Returns (last_price, previous_close, market_cap) using fast_info; safe defaults on failure."""
    try:
        fast = yf_obj.fast_info
        price = float(fast.last_price) if hasattr(fast, "last_price") else 0.0
        prev = float(fast.previous_close) if hasattr(fast, "previous_close") else 0.0
        mkt_cap = float(fast.market_cap) if getattr(fast, "market_cap", None) else None
        return price, prev, mkt_cap
    except Exception:
        return 0.0, 0.0, None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def get_overview(ticker: str) -> dict:
    """Key company info + headline financial metrics."""
    ticker = ticker.upper()
    if ticker in _overview_cache:
        return _overview_cache[ticker]

    yf_obj, ticker, _ = _resolve_ticker(ticker)
    meta = TICKER_TO_META.get(ticker, {})

    try:
        info = yf_obj.info or {}
    except Exception:
        info = {}

    price, prev, mkt_cap = _quote_from_fast_info(yf_obj)
    change = ((price - prev) / prev * 100) if prev else 0.0

    div_yield_raw = info.get("dividendYield")
    roe_raw = info.get("returnOnEquity")

    result = {
        "ticker": ticker,
        "name": meta.get("name", info.get("shortName", ticker)),
        "sector": meta.get("sector", info.get("sector", "—")),
        "industry": info.get("industry", "—"),
        "current_price": round(price, 2),
        "change_percent": round(change, 2),
        "previous_close": round(prev, 2) if prev else None,
        "market_cap": mkt_cap,
        "market_cap_formatted": _fmt_cr(mkt_cap),
        "pe_ratio": _safe_round(info.get("trailingPE")),
        "pb_ratio": _safe_round(info.get("priceToBook")),
        "eps": _safe_round(info.get("trailingEps")),
        "dividend_yield": _safe_round(div_yield_raw * 100) if div_yield_raw else None,
        "book_value": _safe_round(info.get("bookValue")),
        "face_value": info.get("faceValue"),
        "roe": _safe_round(roe_raw * 100) if roe_raw else None,
        "roce": None,  # yfinance does not expose ROCE directly
        "debt_to_equity": _safe_round(info.get("debtToEquity")),
        "high_52w": _safe_round(info.get("fiftyTwoWeekHigh")),
        "low_52w": _safe_round(info.get("fiftyTwoWeekLow")),
        "day_high": _safe_round(info.get("dayHigh")),
        "day_low": _safe_round(info.get("dayLow")),
        "volume": info.get("volume"),
        "avg_volume": info.get("averageVolume"),
        "description": (info.get("longBusinessSummary") or "")[:500],
    }
    _overview_cache[ticker] = result
    return result


def get_financials(ticker: str, period: str = "annual") -> dict:
    """Income statement, balance sheet, cash flow. period ∈ {'annual','quarterly'}."""
    ticker = ticker.upper()
    cache_key = f"{ticker}_{period}"
    if cache_key in _financials_cache:
        return _financials_cache[cache_key]

    yf_obj, ticker, _ = _resolve_ticker(ticker)

    try:
        if period == "quarterly":
            income = yf_obj.quarterly_income_stmt
            balance = yf_obj.quarterly_balance_sheet
            cashflow = yf_obj.quarterly_cashflow
        else:
            income = yf_obj.income_stmt
            balance = yf_obj.balance_sheet
            cashflow = yf_obj.cashflow

        result = {
            "ticker": ticker,
            "period": period,
            "income_statement": _df_to_dict(income),
            "balance_sheet": _df_to_dict(balance),
            "cash_flow": _df_to_dict(cashflow),
        }
        _financials_cache[cache_key] = result
        return result
    except Exception as e:
        logger.error("Financials fetch failed for %s: %s", ticker, e)
        return {
            "ticker": ticker,
            "period": period,
            "income_statement": {},
            "balance_sheet": {},
            "cash_flow": {},
        }


def get_ratios(ticker: str) -> dict:
    """Comprehensive financial ratios bundle."""
    ticker = ticker.upper()
    if ticker in _ratios_cache:
        return _ratios_cache[ticker]

    yf_obj, ticker, _ = _resolve_ticker(ticker)

    try:
        info = yf_obj.info or {}
    except Exception:
        info = {}

    _, _, mkt_cap = _quote_from_fast_info(yf_obj)

    ratios = {
        "ticker": ticker,
        "valuation": {
            "pe_ratio": _safe_round(info.get("trailingPE")),
            "forward_pe": _safe_round(info.get("forwardPE")),
            "pb_ratio": _safe_round(info.get("priceToBook")),
            "ps_ratio": _safe_round(info.get("priceToSalesTrailing12Months")),
            "ev_ebitda": _safe_round(info.get("enterpriseToEbitda")),
            "peg_ratio": _safe_round(info.get("pegRatio")),
            "market_cap": _fmt_cr(mkt_cap),
            "enterprise_value": _fmt_cr(info.get("enterpriseValue")),
        },
        "profitability": {
            "roe": _pct(info.get("returnOnEquity")),
            "roa": _pct(info.get("returnOnAssets")),
            "profit_margin": _pct(info.get("profitMargins")),
            "operating_margin": _pct(info.get("operatingMargins")),
            "gross_margin": _pct(info.get("grossMargins")),
            "eps": _safe_round(info.get("trailingEps")),
        },
        "growth": {
            "revenue_growth": _pct(info.get("revenueGrowth")),
            "earnings_growth": _pct(info.get("earningsGrowth")),
            "quarterly_revenue_growth": _pct(info.get("revenueQuarterlyGrowth")),
            "quarterly_earnings_growth": _pct(info.get("earningsQuarterlyGrowth")),
        },
        "financial_health": {
            "debt_to_equity": _safe_round(info.get("debtToEquity")),
            "current_ratio": _safe_round(info.get("currentRatio")),
            "quick_ratio": _safe_round(info.get("quickRatio")),
            "total_debt": _fmt_cr(info.get("totalDebt")),
            "total_cash": _fmt_cr(info.get("totalCash")),
        },
        "dividends": {
            "dividend_yield": _pct(info.get("dividendYield")),
            "dividend_rate": _safe_round(info.get("dividendRate")),
            "payout_ratio": _pct(info.get("payoutRatio")),
        },
    }
    _ratios_cache[ticker] = ratios
    return ratios


def get_peers(ticker: str, max_peers: int = 6) -> dict:
    """Same-sector peer comparison on key metrics. Target ticker is included with is_target=True."""
    ticker = ticker.upper()
    cache_key = f"{ticker}_{max_peers}"
    if cache_key in _peers_cache:
        return _peers_cache[cache_key]

    meta = TICKER_TO_META.get(ticker)
    if not meta:
        raise LookupError(f"Ticker '{ticker}' not found in NSE universe")

    sector = meta["sector"]
    peer_metas = [s for s in NSE_STOCKS if s["sector"] == sector and s["ticker"] != ticker][:max_peers]

    universe = [{"ticker": ticker, **meta}, *[
        {"ticker": p["ticker"], "name": p["name"], "sector": p["sector"]} for p in peer_metas
    ]]

    rows: list[dict] = []
    for p in universe:
        t = p["ticker"]
        try:
            yf_obj = yf.Ticker(resolve_yf_symbol(t))
            info = yf_obj.info or {}
            price, _, mkt_cap = _quote_from_fast_info(yf_obj)

            rows.append({
                "ticker": t,
                "name": p["name"],
                "current_price": round(price, 2),
                "market_cap": _fmt_cr(mkt_cap),
                "pe_ratio": _safe_round(info.get("trailingPE")),
                "pb_ratio": _safe_round(info.get("priceToBook")),
                "roe": _pct(info.get("returnOnEquity")),
                "profit_margin": _pct(info.get("profitMargins")),
                "debt_to_equity": _safe_round(info.get("debtToEquity")),
                "dividend_yield": _pct(info.get("dividendYield")),
                "is_target": t == ticker,
            })
        except Exception as e:
            logger.warning("Peer data failed for %s: %s", t, e)
            rows.append({
                "ticker": t,
                "name": p["name"],
                "current_price": 0.0,
                "market_cap": "—",
                "pe_ratio": None,
                "pb_ratio": None,
                "roe": None,
                "profit_margin": None,
                "debt_to_equity": None,
                "dividend_yield": None,
                "is_target": t == ticker,
            })

    result = {"ticker": ticker, "sector": sector, "peers": rows}
    _peers_cache[cache_key] = result
    return result


def get_shareholding(ticker: str) -> dict:
    """Promoter / FII / DII breakdown plus top institutional holders."""
    ticker = ticker.upper()
    if ticker in _holders_cache:
        return _holders_cache[ticker]

    yf_obj, ticker, _ = _resolve_ticker(ticker)

    major: list[dict] = []
    try:
        holders = yf_obj.major_holders
        if holders is not None and not holders.empty:
            for _, row in holders.iterrows():
                major.append({"label": str(row.iloc[1]), "value": str(row.iloc[0])})
    except Exception as e:
        logger.warning("Major holders fetch failed for %s: %s", ticker, e)

    top_inst: list[dict] = []
    try:
        inst = yf_obj.institutional_holders
        if inst is not None and not inst.empty:
            for _, row in inst.head(5).iterrows():
                pct_held = row.get("pctHeld", row.get("% Out"))
                top_inst.append({
                    "holder": str(row.get("Holder", "")),
                    "shares": int(row.get("Shares", 0)),
                    "pct_out": _safe_round(pct_held * 100) if pct_held else None,
                })
    except Exception as e:
        logger.warning("Institutional holders fetch failed for %s: %s", ticker, e)

    result = {"ticker": ticker, "major_holders": major, "top_institutions": top_inst}
    _holders_cache[ticker] = result
    return result
