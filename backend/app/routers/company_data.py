"""
Company Data Router
====================
Endpoints for detailed company information — financials,
ratios, peer comparison, shareholding. Powered by yfinance.
"""

import yfinance as yf
import logging
from cachetools import TTLCache
from fastapi import APIRouter, HTTPException
from app.nse_universe import TICKER_TO_YF, TICKER_TO_META, NSE_STOCKS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/company", tags=["company"])

# Caches
_overview_cache = TTLCache(maxsize=100, ttl=600)    # 10 min
_financials_cache = TTLCache(maxsize=50, ttl=1800)  # 30 min
_holders_cache = TTLCache(maxsize=50, ttl=3600)     # 1 hour


def _get_yf_ticker(ticker: str):
    """Get yfinance Ticker object for an NSE ticker."""
    ticker = ticker.upper()
    yf_symbol = TICKER_TO_YF.get(ticker)
    if not yf_symbol:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found")
    return yf.Ticker(yf_symbol), ticker


# -----------------------------------------------------------------------
# Overview
# -----------------------------------------------------------------------
@router.get("/{ticker}/overview")
async def get_company_overview(ticker: str):
    """Key company info + financial metrics."""
    ticker = ticker.upper()
    cache_key = f"overview_{ticker}"
    if cache_key in _overview_cache:
        return _overview_cache[cache_key]

    yf_obj, _ = _get_yf_ticker(ticker)
    meta = TICKER_TO_META.get(ticker, {})

    try:
        info = yf_obj.info or {}
    except Exception:
        info = {}

    try:
        fast = yf_obj.fast_info
        price = float(fast.last_price) if hasattr(fast, "last_price") else 0
        prev = float(fast.previous_close) if hasattr(fast, "previous_close") else 0
        change = ((price - prev) / prev * 100) if prev else 0
        mkt_cap = float(fast.market_cap) if hasattr(fast, "market_cap") and fast.market_cap else None
    except Exception:
        price, change, mkt_cap = 0, 0, None

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
        "dividend_yield": _safe_round(info.get("dividendYield", 0) * 100 if info.get("dividendYield") else None),
        "book_value": _safe_round(info.get("bookValue")),
        "face_value": info.get("faceValue"),
        "roe": _safe_round(info.get("returnOnEquity", 0) * 100 if info.get("returnOnEquity") else None),
        "roce": None,  # yfinance doesn't directly provide ROCE
        "debt_to_equity": _safe_round(info.get("debtToEquity")),
        "high_52w": _safe_round(info.get("fiftyTwoWeekHigh")),
        "low_52w": _safe_round(info.get("fiftyTwoWeekLow")),
        "day_high": _safe_round(info.get("dayHigh")),
        "day_low": _safe_round(info.get("dayLow")),
        "volume": info.get("volume"),
        "avg_volume": info.get("averageVolume"),
        "description": (info.get("longBusinessSummary") or "")[:500],
    }
    _overview_cache[cache_key] = result
    return result


# -----------------------------------------------------------------------
# Financials
# -----------------------------------------------------------------------
@router.get("/{ticker}/financials")
async def get_company_financials(ticker: str, period: str = "annual"):
    """
    Income Statement, Balance Sheet, Cash Flow.
    period: 'annual' or 'quarterly'
    """
    ticker = ticker.upper()
    cache_key = f"fin_{ticker}_{period}"
    if cache_key in _financials_cache:
        return _financials_cache[cache_key]

    yf_obj, _ = _get_yf_ticker(ticker)

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
        logger.error(f"Financials fetch failed for {ticker}: {e}")
        return {"ticker": ticker, "period": period, "income_statement": {}, "balance_sheet": {}, "cash_flow": {}}


# -----------------------------------------------------------------------
# Key Ratios
# -----------------------------------------------------------------------
@router.get("/{ticker}/ratios")
async def get_company_ratios(ticker: str):
    """Comprehensive financial ratios."""
    ticker = ticker.upper()
    yf_obj, _ = _get_yf_ticker(ticker)

    try:
        info = yf_obj.info or {}
    except Exception:
        info = {}

    try:
        fast = yf_obj.fast_info
        price = float(fast.last_price) if hasattr(fast, "last_price") else 0
        mkt_cap = float(fast.market_cap) if hasattr(fast, "market_cap") and fast.market_cap else None
    except Exception:
        price, mkt_cap = 0, None

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
    return ratios


# -----------------------------------------------------------------------
# Peer Comparison
# -----------------------------------------------------------------------
@router.get("/{ticker}/peers")
async def get_peer_comparison(ticker: str):
    """Compare with same-sector stocks on key metrics."""
    ticker = ticker.upper()
    meta = TICKER_TO_META.get(ticker)
    if not meta:
        raise HTTPException(status_code=404, detail="Ticker not found")

    sector = meta["sector"]
    peers = [s for s in NSE_STOCKS if s["sector"] == sector and s["ticker"] != ticker][:6]

    results = []
    for p in [{"ticker": ticker, **meta}, *[{"ticker": pe["ticker"], "name": pe["name"], "sector": pe["sector"]} for pe in peers]]:
        t = p["ticker"]
        try:
            yf_obj = yf.Ticker(TICKER_TO_YF[t])
            info = yf_obj.info or {}
            fast = yf_obj.fast_info
            price = float(fast.last_price) if hasattr(fast, "last_price") else 0
            mkt_cap = float(fast.market_cap) if hasattr(fast, "market_cap") and fast.market_cap else None

            results.append({
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
            logger.warning(f"Peer data failed for {t}: {e}")
            results.append({
                "ticker": t, "name": p["name"],
                "current_price": 0, "market_cap": "—",
                "pe_ratio": None, "pb_ratio": None, "roe": None,
                "profit_margin": None, "debt_to_equity": None,
                "dividend_yield": None, "is_target": t == ticker,
            })

    return {"ticker": ticker, "sector": sector, "peers": results}


# -----------------------------------------------------------------------
# Shareholding
# -----------------------------------------------------------------------
@router.get("/{ticker}/shareholding")
async def get_shareholding(ticker: str):
    """Promoter, FII, DII breakdown."""
    ticker = ticker.upper()
    cache_key = f"holders_{ticker}"
    if cache_key in _holders_cache:
        return _holders_cache[cache_key]

    yf_obj, _ = _get_yf_ticker(ticker)

    try:
        holders = yf_obj.major_holders
        if holders is not None and not holders.empty:
            data = []
            for _, row in holders.iterrows():
                data.append({"label": str(row.iloc[1]), "value": str(row.iloc[0])})
        else:
            data = []
    except Exception as e:
        logger.warning(f"Holders fetch failed for {ticker}: {e}")
        data = []

    try:
        inst = yf_obj.institutional_holders
        if inst is not None and not inst.empty:
            top_inst = []
            for _, row in inst.head(5).iterrows():
                top_inst.append({
                    "holder": str(row.get("Holder", "")),
                    "shares": int(row.get("Shares", 0)),
                    "pct_out": _safe_round(row.get("pctHeld", row.get("% Out", 0)) * 100 if row.get("pctHeld", row.get("% Out")) else None),
                })
        else:
            top_inst = []
    except Exception:
        top_inst = []

    result = {"ticker": ticker, "major_holders": data, "top_institutions": top_inst}
    _holders_cache[cache_key] = result
    return result


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------
def _safe_round(val, digits=2):
    if val is None:
        return None
    try:
        return round(float(val), digits)
    except (ValueError, TypeError):
        return None


def _pct(val):
    """Convert decimal ratio to percentage, handling None."""
    if val is None:
        return None
    try:
        return round(float(val) * 100, 2)
    except (ValueError, TypeError):
        return None


def _fmt_cr(val):
    """Format value in Crores (₹Cr)."""
    if val is None:
        return "—"
    try:
        v = float(val)
        cr = v / 1e7
        if cr >= 100000:
            return f"₹{cr/100000:.2f}L Cr"
        elif cr >= 1000:
            return f"₹{cr/1000:.2f}K Cr"
        else:
            return f"₹{cr:.0f} Cr"
    except (ValueError, TypeError):
        return "—"


def _df_to_dict(df):
    """Convert a pandas DataFrame from yfinance to a JSON-friendly dict."""
    if df is None or df.empty:
        return {}
    result = {}
    for col in df.columns:
        col_label = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)
        col_data = {}
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
