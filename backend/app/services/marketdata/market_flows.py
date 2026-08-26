"""
Market Flows Service
====================
Daily FII (Foreign Institutional Investor) / DII (Domestic Institutional Investor)
activity from NSE's official `fiidiiTradeReact` JSON endpoint.

Why NSE and not moneycontrol: moneycontrol's daily page is now a Next.js SPA
that ships an empty HTML shell — no FII/DII numbers exist in the raw response.
NSE's API returns clean JSON when called with a browser-like User-Agent and an
nseindia.com Referer.

Cached 6 h since the data is end-of-day. Graceful — every public call returns
None on failure so the rest of the app continues without flow signals.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests
from cachetools import TTLCache

logger = logging.getLogger(__name__)

_flows_cache: TTLCache = TTLCache(maxsize=1, ttl=21600)   # 6 h positive
_flows_neg_cache: TTLCache = TTLCache(maxsize=1, ttl=300)  # 5 min negative

_NSE_FII_DII_URL = "https://www.nseindia.com/api/fiidiiTradeReact"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/reports/fii-dii",
    "X-Requested-With": "XMLHttpRequest",
    "Connection": "keep-alive",
}

_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def _parse_num(v) -> float | None:
    if v is None:
        return None
    try:
        return round(float(str(v).replace(",", "").strip()), 2)
    except (ValueError, TypeError):
        return None


def _parse_nse_date(s: str) -> str | None:
    """NSE returns dates like '12-May-2026'. Convert to ISO YYYY-MM-DD."""
    if not s:
        return None
    parts = s.split("-")
    if len(parts) != 3:
        return None
    try:
        day = int(parts[0])
        mon = _MONTHS.get(parts[1][:3].title())
        year = int(parts[2])
        if not mon:
            return None
        return f"{year:04d}-{mon:02d}-{day:02d}"
    except (ValueError, TypeError):
        return None


def fetch_latest_flows() -> dict | None:
    """Return the most recent FII/DII row, or None on failure.

    Shape: {
      date:        "YYYY-MM-DD",
      fii_buy_cr, fii_sell_cr, fii_net_cr,
      dii_buy_cr, dii_sell_cr, dii_net_cr,
      net_inr_cr,                         # combined FII + DII net (summary)
      source: "nse",
      fetched_at: ISO,
    }

    Cached 6 h positive, 5 min negative.
    """
    if "latest" in _flows_cache:
        return _flows_cache["latest"]
    if "latest" in _flows_neg_cache:
        return None

    try:
        # Some IPs need a cookie warm-up; others succeed directly. Try the API
        # call first, fall back to a session-warm retry on 401/403.
        resp = requests.get(_NSE_FII_DII_URL, headers=_HEADERS, timeout=15)
        if resp.status_code in (401, 403):
            sess = requests.Session()
            try:
                sess.get(
                    "https://www.nseindia.com/",
                    headers={"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"},
                    timeout=15,
                )
            except Exception:
                pass
            resp = sess.get(_NSE_FII_DII_URL, headers=_HEADERS, timeout=15)
        if resp.status_code != 200:
            _flows_neg_cache["latest"] = True
            return None

        data = resp.json()
        if not isinstance(data, list) or not data:
            _flows_neg_cache["latest"] = True
            return None

        fii_row: dict = {}
        dii_row: dict = {}
        for row in data:
            cat = (row.get("category") or "").upper()
            if "FII" in cat or "FPI" in cat:
                fii_row = row
            elif "DII" in cat:
                dii_row = row

        date_iso = _parse_nse_date(fii_row.get("date") or dii_row.get("date") or "")
        fii_net = _parse_num(fii_row.get("netValue"))
        dii_net = _parse_num(dii_row.get("netValue"))
        net_combined: float | None = None
        if fii_net is not None and dii_net is not None:
            net_combined = round(fii_net + dii_net, 1)

        out = {
            "date": date_iso,
            "fii_buy_cr":  _parse_num(fii_row.get("buyValue")),
            "fii_sell_cr": _parse_num(fii_row.get("sellValue")),
            "fii_net_cr":  fii_net,
            "dii_buy_cr":  _parse_num(dii_row.get("buyValue")),
            "dii_sell_cr": _parse_num(dii_row.get("sellValue")),
            "dii_net_cr":  dii_net,
            "net_inr_cr":  net_combined,
            "source": "nse",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        # Need at least one net to be useful
        if fii_net is None and dii_net is None:
            _flows_neg_cache["latest"] = True
            return None
        _flows_cache["latest"] = out
        return out
    except Exception as e:
        logger.warning("FII/DII fetch failed: %s", e)
        _flows_neg_cache["latest"] = True
        return None


def is_available() -> bool:
    """Always returns True — per-call cache handles failures."""
    return True


def summarize_for_prompt(flows: dict | None) -> str | None:
    """One-line summary for LLM context.

    Example: "FII net -1,959 cr (selling); DII net +7,990 cr (buying) on 2026-05-12"
    """
    if not flows:
        return None

    def _fmt(n: float | None) -> str:
        if n is None:
            return "n/a"
        sign = "+" if n >= 0 else ""
        return f"{sign}{n:,.0f} cr"

    fii = flows.get("fii_net_cr")
    dii = flows.get("dii_net_cr")
    def _side(v):
        return "buying" if v and v > 0 else "selling" if v and v < 0 else "flat"
    return (
        f"FII net {_fmt(fii)} ({_side(fii)}); "
        f"DII net {_fmt(dii)} ({_side(dii)}) on {flows.get('date')}"
    )
