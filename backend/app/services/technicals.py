"""
Technicals Service
==================
Lightweight technical signals (RSI, volume-vs-avg, MA position, momentum,
position-in-range) computed from yfinance OHLCV. Used as additional grounding
context in LLM attribution prompts — answers questions like "did volume confirm
the move?", "is RSI stretched?", "near 20d high or breaking down?".

We compute only what we actually consume downstream — not a charting library.
Split positive/negative TTL cache mirrors grounding._fetch_snapshot so the
yfinance shared-IP rate-limit on Render doesn't keep biting.
"""

from __future__ import annotations

import logging
import time as _time

import yfinance as yf
from cachetools import TTLCache

from app.nse_universe import TICKER_TO_YF, resolve_yf_symbol
from app.services import yf_safe

logger = logging.getLogger(__name__)

_tech_cache: TTLCache = TTLCache(maxsize=300, ttl=1800)   # 30 min positive
# Two-tier neg cache: delisted/no-data symbols hold 24h; transient errors 60s.
# Without this split, a permanently delisted ticker would re-cost the yfinance
# retry tax every minute, dragging every Context Engine call.
_tech_neg_perm: TTLCache = TTLCache(maxsize=500, ttl=yf_safe.NEG_TTL_PERMANENT_S)
_tech_neg_transient: TTLCache = TTLCache(maxsize=300, ttl=yf_safe.NEG_TTL_TRANSIENT_S)


def _rsi(closes: list[float], period: int = 14) -> float | None:
    """Wilder-smoothed RSI. Needs at least `period + 1` closes; we give it 30."""
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains.append(d if d > 0 else 0.0)
        losses.append(-d if d < 0 else 0.0)
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        gain = d if d > 0 else 0.0
        loss = -d if d < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)


def _pct_change(a: float | None, b: float | None) -> float | None:
    if a is None or not b:
        return None
    return round((a - b) / b * 100, 2)


def compute_signals(ticker: str) -> dict | None:
    """Compute technical signals for one ticker. Returns dict on success,
    None on failure (unknown ticker / yfinance rate-limited / not enough bars).

    Cached 30 min positive / 60 s negative. Keys returned:
      rsi14, rsi_zone (oversold|weak|neutral|strong|overbought)
      vol_vs_avg20, vol_zone (low|normal|high|surge)
      pct_from_sma20, pct_from_sma50, sma_state
      momentum_5d_pct, momentum_20d_pct, momentum_state
      pct_from_20d_high, pct_from_20d_low
    """
    if ticker in _tech_cache:
        return _tech_cache[ticker]
    if ticker in _tech_neg_perm or ticker in _tech_neg_transient:
        return None
    yf_symbol = resolve_yf_symbol(ticker)
    if not yf_symbol:
        _tech_neg_perm[ticker] = True
        return None

    def _inner() -> dict | None:
        tk = yf.Ticker(yf_symbol)
        hist = tk.history(period="3mo", auto_adjust=False)
        if hist is None or hist.empty or len(hist) < 21:
            return None

        closes = [float(c) for c in hist["Close"].dropna().tolist()]
        vols = [float(v) for v in hist["Volume"].dropna().tolist()]
        if len(closes) < 21:
            return None

        close = closes[-1]
        sma20 = sum(closes[-20:]) / 20
        sma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else None
        avg_vol20 = sum(vols[-20:]) / 20 if len(vols) >= 20 else None
        today_vol = vols[-1] if vols else None
        vol_vs_avg20 = (
            round(today_vol / avg_vol20, 2)
            if (avg_vol20 and avg_vol20 > 0 and today_vol)
            else None
        )

        rsi14 = _rsi(closes[-30:], 14) if len(closes) >= 30 else None
        mom_5d = _pct_change(close, closes[-6]) if len(closes) >= 6 else None
        mom_20d = _pct_change(close, closes[-21]) if len(closes) >= 21 else None
        high_20d = max(closes[-20:])
        low_20d = min(closes[-20:])

        rsi_zone = "neutral"
        if rsi14 is not None:
            if rsi14 >= 70:   rsi_zone = "overbought"
            elif rsi14 >= 60: rsi_zone = "strong"
            elif rsi14 <= 30: rsi_zone = "oversold"
            elif rsi14 <= 40: rsi_zone = "weak"

        vol_zone = "normal"
        if vol_vs_avg20 is not None:
            if vol_vs_avg20 >= 2.0:   vol_zone = "surge"
            elif vol_vs_avg20 >= 1.4: vol_zone = "high"
            elif vol_vs_avg20 <= 0.6: vol_zone = "low"

        sma_state = None
        if sma50 is not None:
            sma_state = "above_sma50" if close > sma50 else "below_sma50"

        momentum_state = "consolidating"
        if mom_5d is not None and mom_20d is not None:
            if mom_5d > 1 and mom_20d > 3:     momentum_state = "extending_up"
            elif mom_5d < -1 and mom_20d < -3: momentum_state = "extending_down"
            elif mom_5d > 0 and mom_20d < 0:   momentum_state = "reversing_up"
            elif mom_5d < 0 and mom_20d > 0:   momentum_state = "reversing_down"

        return {
            "rsi14": rsi14,
            "rsi_zone": rsi_zone,
            "vol_vs_avg20": vol_vs_avg20,
            "vol_zone": vol_zone,
            "pct_from_sma20": _pct_change(close, sma20),
            "pct_from_sma50": _pct_change(close, sma50) if sma50 else None,
            "sma_state": sma_state,
            "momentum_5d_pct": mom_5d,
            "momentum_20d_pct": mom_20d,
            "momentum_state": momentum_state,
            "pct_from_20d_high": _pct_change(close, high_20d),
            "pct_from_20d_low": _pct_change(close, low_20d),
        }

    # 6s budget — history(period="3mo") is heavier than fast_info but still
    # bounded. Wrapping in yf_safe means a delisted symbol's retry storm
    # can't stall a worker for 30s.
    result, ok = yf_safe.run_with_timeout(_inner, timeout_s=6.0)
    if not ok:
        exc = result if isinstance(result, Exception) else None
        kind = yf_safe.classify_error(exc, None if exc is None else "__sentinel__")
        if kind == "permanent":
            _tech_neg_perm[ticker] = True
        else:
            _tech_neg_transient[ticker] = True
        if exc is not None:
            logger.warning("technical signals failed for %s: %s", ticker, exc)
        return None
    if result is None:
        # Empty history → almost certainly delisted/unknown.
        _tech_neg_perm[ticker] = True
        return None
    _tech_cache[ticker] = result
    return result


def compute_signals_batch(tickers: list[str]) -> dict[str, dict]:
    """Convenience: compute signals for many tickers. Skips unknown/failures."""
    out: dict[str, dict] = {}
    for t in tickers:
        sig = compute_signals(t)
        if sig is not None:
            out[t] = sig
    return out


def summarize_for_prompt(sig: dict | None) -> str | None:
    """One-line human/LLM-friendly summary of the signals. None if no data.

    Example output:
      "RSI 72 (overbought); vol 1.8x avg (high); above SMA50; momentum extending_up
       (5d +2.4%, 20d +9.1%); -1.2% from 20d high"
    """
    if not sig:
        return None
    parts: list[str] = []
    if sig.get("rsi14") is not None:
        parts.append(f"RSI {sig['rsi14']} ({sig.get('rsi_zone')})")
    if sig.get("vol_vs_avg20") is not None:
        parts.append(f"vol {sig['vol_vs_avg20']}x avg ({sig.get('vol_zone')})")
    if sig.get("sma_state"):
        parts.append(sig["sma_state"].replace("_", " "))
    mom5, mom20 = sig.get("momentum_5d_pct"), sig.get("momentum_20d_pct")
    if mom5 is not None or mom20 is not None:
        bits = []
        if mom5 is not None:  bits.append(f"5d {mom5:+}%")
        if mom20 is not None: bits.append(f"20d {mom20:+}%")
        parts.append(f"momentum {sig.get('momentum_state')} ({', '.join(bits)})")
    p20h = sig.get("pct_from_20d_high")
    if p20h is not None:
        parts.append(f"{p20h:+}% from 20d high")
    return "; ".join(parts) if parts else None
