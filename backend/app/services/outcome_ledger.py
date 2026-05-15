"""
Outcome Ledger
==============
Records every forward-looking AI prediction the system makes (Tomorrow
per-holding watch items + News Impact items) and computes whether the
predicted direction matched the actual price move 1d / 5d / 20d later.

Backed by Supabase tables `ai_predictions` + `prediction_outcomes`
(migration 004_outcome_ledger.sql). Reads/writes via the service-role key.

Public functions:
    log_predictions(items)              — bulk-upsert prediction rows
    compute_pending_outcomes()          — fill in outcomes for due predictions
    accuracy_summary(...)               — aggregate hit-rate breakdowns
    recent_results(limit)               — recent (prediction, outcome) rows

Every call is best-effort. Failures are logged + swallowed so the rest of the
app keeps working with no ledger (just no accuracy page).
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timezone, timedelta
from typing import Any, Iterable

import yfinance as yf
from dotenv import load_dotenv

from app.nse_universe import TICKER_TO_YF, resolve_yf_symbol

logger = logging.getLogger(__name__)
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

_client = None
if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    try:
        from supabase import create_client
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        logger.info("Supabase outcome_ledger client initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client in outcome_ledger: {e}")


# Horizons we score against — calendar-day offsets. Trading-day arithmetic
# happens via yfinance's history (which only returns trading days), so a `5d`
# horizon means "5 trading days later" not "5 calendar days later" — closer to
# what an investor would actually compare.
HORIZONS_TD = {"1d": 1, "5d": 5, "20d": 20}

# Absolute % move required for a directional call (positive/negative) to count
# as a hit. Anything smaller is "drift" and credited to the neutral bucket.
HIT_THRESHOLD_PCT = 0.5


def is_available() -> bool:
    return _client is not None


# ---------------------------------------------------------------------------
# Logging — write new predictions
# ---------------------------------------------------------------------------
def log_predictions(items: list[dict]) -> int:
    """Upsert a batch of prediction rows. Each item must have:
        ticker, source, direction
    Optional fields:
        prediction_date (defaults to today UTC), impact_level, catalyst_type,
        reason, cited_sources, technical_state, price_at_call, dedup_key, metadata

    `dedup_key` is used to UPSERT — same key replaces the existing row. Use
    deterministic keys so re-running an endpoint the same day doesn't create
    duplicate entries.

    Returns rows written, or 0 if the client is down. Never raises.
    """
    if not _client or not items:
        return 0

    rows: list[dict] = []
    for it in items:
        ticker = (it.get("ticker") or "").upper()
        direction = it.get("direction")
        if not ticker or not direction:
            continue
        pd = it.get("prediction_date") or date.today()
        if hasattr(pd, "isoformat"):
            pd_str = pd.isoformat()
        else:
            pd_str = str(pd)[:10]
        row = {
            "ticker": ticker,
            "prediction_date": pd_str,
            "source": it.get("source") or "unknown",
            "direction": direction,
            "impact_level": it.get("impact_level"),
            "catalyst_type": it.get("catalyst_type"),
            "reason": (it.get("reason") or "").strip()[:500] or None,
            "cited_sources": it.get("cited_sources") or [],
            "technical_state": it.get("technical_state"),
            "price_at_call": it.get("price_at_call"),
            "dedup_key": it.get("dedup_key"),
            "metadata": it.get("metadata"),
        }
        rows.append(row)

    if not rows:
        return 0

    # Split by whether dedup_key is present — upsert keyed rows, insert the rest.
    keyed = [r for r in rows if r.get("dedup_key")]
    unkeyed = [r for r in rows if not r.get("dedup_key")]
    written = 0
    try:
        if keyed:
            _client.table("ai_predictions").upsert(keyed, on_conflict="dedup_key").execute()
            written += len(keyed)
        if unkeyed:
            _client.table("ai_predictions").insert(unkeyed).execute()
            written += len(unkeyed)
    except Exception as e:
        logger.warning("log_predictions failed: %s", e)
    return written


# ---------------------------------------------------------------------------
# Outcome computation — fill in price/return/hit for due predictions
# ---------------------------------------------------------------------------
def _fetch_price_history(ticker: str, start_date: date) -> dict[str, float]:
    """Return {iso_date: close_price} for `ticker` from `start_date` to today.
    Only trading days. Empty dict on failure.
    """
    yf_symbol = resolve_yf_symbol(ticker)
    if not yf_symbol:
        return {}
    try:
        tk = yf.Ticker(yf_symbol)
        hist = tk.history(start=start_date.isoformat(), auto_adjust=False)
        if hist is None or hist.empty:
            return {}
        out: dict[str, float] = {}
        for idx, row in hist.iterrows():
            d = idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10]
            close = row.get("Close")
            if close is not None:
                out[d] = float(close)
        return out
    except Exception as e:
        logger.debug("price history fetch failed for %s: %s", ticker, e)
        return {}


def _hit_rule(direction: str, return_pct: float) -> bool:
    """Determine whether a prediction was a hit.

    - 'positive' / 'negative' — directional: sign must match and |return| ≥ threshold
    - 'neutral'              — |return| must be < threshold
    - 'mixed'                — never counts as hit OR miss (treated as N/A by callers)
    """
    if return_pct is None:
        return False
    if direction == "positive":
        return return_pct >= HIT_THRESHOLD_PCT
    if direction == "negative":
        return return_pct <= -HIT_THRESHOLD_PCT
    if direction == "neutral":
        return abs(return_pct) < HIT_THRESHOLD_PCT
    return False  # mixed / unknown


def compute_pending_outcomes() -> dict:
    """For every (prediction, horizon) pair that doesn't yet have an outcome
    AND has enough trading days elapsed, compute the return + hit flag.

    Returns: { processed, written, skipped, by_horizon: {...}, errors }
    """
    if not _client:
        return {"error": "supabase client unavailable"}

    today = datetime.now(timezone.utc).date()
    summary = {"processed": 0, "written": 0, "skipped": 0, "by_horizon": {}, "errors": 0}

    # Pull predictions that are old enough for at least the 1d horizon
    # (i.e. prediction_date < today). Limit to last 90 days to keep the job
    # bounded; older predictions get caught up by repeated daily runs.
    cutoff_oldest = (today - timedelta(days=90)).isoformat()
    cutoff_recent = today.isoformat()

    try:
        res = (
            _client.table("ai_predictions")
            .select("id,ticker,prediction_date,direction,price_at_call")
            .gte("prediction_date", cutoff_oldest)
            .lt("prediction_date", cutoff_recent)
            .execute()
        )
        predictions = res.data or []
    except Exception as e:
        logger.warning("compute_pending_outcomes: fetch predictions failed: %s", e)
        summary["errors"] += 1
        return summary

    if not predictions:
        return summary

    # Find which (prediction, horizon) pairs already have outcomes — skip those.
    pred_ids = [p["id"] for p in predictions]
    already_done: set[tuple[str, str]] = set()
    try:
        # Supabase has a 1000-row IN limit by default; chunk it.
        for i in range(0, len(pred_ids), 500):
            chunk = pred_ids[i:i + 500]
            r = (
                _client.table("prediction_outcomes")
                .select("prediction_id,horizon")
                .in_("prediction_id", chunk)
                .execute()
            )
            for row in (r.data or []):
                already_done.add((row["prediction_id"], row["horizon"]))
    except Exception as e:
        logger.warning("compute_pending_outcomes: fetch existing outcomes failed: %s", e)

    # Group predictions by ticker so we make one yfinance call per ticker.
    by_ticker: dict[str, list[dict]] = {}
    for p in predictions:
        by_ticker.setdefault(p["ticker"], []).append(p)

    to_insert: list[dict] = []
    for ticker, preds in by_ticker.items():
        # Earliest prediction date for this ticker drives how far back to fetch.
        earliest = min((p["prediction_date"] for p in preds), default=None)
        if not earliest:
            continue
        try:
            start = date.fromisoformat(earliest) - timedelta(days=2)
        except Exception:
            start = today - timedelta(days=30)

        history = _fetch_price_history(ticker, start)
        if not history:
            summary["skipped"] += len(preds) * len(HORIZONS_TD)
            continue

        # Pre-sort dates so we can look up "N trading days after X" quickly.
        sorted_dates = sorted(history.keys())

        for p in preds:
            try:
                pred_dt = date.fromisoformat(p["prediction_date"])
            except Exception:
                continue

            # Find the index of the prediction date or first trading day after it.
            anchor_idx = None
            for i, d in enumerate(sorted_dates):
                if d >= pred_dt.isoformat():
                    anchor_idx = i
                    break
            if anchor_idx is None:
                summary["skipped"] += len(HORIZONS_TD)
                continue

            anchor_price = p.get("price_at_call") or history.get(sorted_dates[anchor_idx])
            if not anchor_price:
                continue

            for h_label, h_td in HORIZONS_TD.items():
                key = (p["id"], h_label)
                if key in already_done:
                    continue
                summary["processed"] += 1
                target_idx = anchor_idx + h_td
                if target_idx >= len(sorted_dates):
                    summary["skipped"] += 1  # not enough trading days elapsed yet
                    continue
                target_price = history[sorted_dates[target_idx]]
                ret = round((target_price - float(anchor_price)) / float(anchor_price) * 100, 2)
                hit = _hit_rule(p["direction"], ret) if p["direction"] != "mixed" else None
                to_insert.append({
                    "prediction_id": p["id"],
                    "horizon": h_label,
                    "price_at_horizon": round(target_price, 2),
                    "return_pct": ret,
                    "hit": hit,
                })
                summary["by_horizon"][h_label] = summary["by_horizon"].get(h_label, 0) + 1

    if to_insert:
        # Bulk-insert in chunks (Supabase has a payload size limit).
        for i in range(0, len(to_insert), 500):
            chunk = to_insert[i:i + 500]
            try:
                _client.table("prediction_outcomes").upsert(
                    chunk, on_conflict="prediction_id,horizon"
                ).execute()
                summary["written"] += len(chunk)
            except Exception as e:
                logger.warning("compute_pending_outcomes: insert chunk failed: %s", e)
                summary["errors"] += 1

    return summary


# ---------------------------------------------------------------------------
# Aggregation — accuracy summary + recent results for the UI
# ---------------------------------------------------------------------------
def accuracy_summary(
    horizon: str = "1d",
    source: str | None = None,
    impact_level: str | None = None,
    days: int = 30,
) -> dict:
    """Return aggregate accuracy stats for predictions in the last `days` days
    at the chosen `horizon`. Filters: source, impact_level.

    Returned shape:
      {
        horizon, days, filters,
        total, scored,           # scored = excludes pending + 'mixed' direction
        hits, hit_rate_pct,
        avg_return_pct,
        by_impact:   { high: {scored, hits, hit_rate}, ... },
        by_source:   { tomorrow_per_holding: {...}, news_feed: {...} },
        by_direction:{ positive: {...}, negative: {...}, neutral: {...} },
        by_catalyst: { earnings: {...}, news: {...}, ... },
      }
    """
    if not _client:
        return {"error": "supabase client unavailable"}

    today = datetime.now(timezone.utc).date()
    from_date = (today - timedelta(days=days)).isoformat()

    q = (
        _client.table("prediction_results")
        .select("id,ticker,prediction_date,source,impact_level,direction,catalyst_type,horizon,return_pct,hit")
        .eq("horizon", horizon)
        .gte("prediction_date", from_date)
    )
    if source:
        q = q.eq("source", source)
    if impact_level:
        q = q.eq("impact_level", impact_level)

    try:
        rows = q.limit(10000).execute().data or []
    except Exception as e:
        logger.warning("accuracy_summary fetch failed: %s", e)
        return {"error": str(e)}

    def _bucket(rows_subset: list[dict]) -> dict:
        scored = [r for r in rows_subset if r.get("hit") is not None]
        hits = sum(1 for r in scored if r["hit"])
        rets = [r["return_pct"] for r in scored if r.get("return_pct") is not None]
        avg_ret = round(sum(rets) / len(rets), 2) if rets else None
        return {
            "total": len(rows_subset),
            "scored": len(scored),
            "hits": hits,
            "hit_rate_pct": round(100 * hits / len(scored), 1) if scored else None,
            "avg_return_pct": avg_ret,
        }

    def _group(rows_subset, key) -> dict:
        groups: dict[str, list[dict]] = {}
        for r in rows_subset:
            k = r.get(key) or "unknown"
            groups.setdefault(k, []).append(r)
        return {k: _bucket(v) for k, v in groups.items()}

    summary = _bucket(rows)

    # Pending-predictions stats. Useful to drive the empty-state UI: the moment
    # the user runs the Context Engine these counts go up, even before any
    # outcome has been computed. Keeps the Accuracy page from looking dead while
    # the daily cron hasn't yet caught up.
    predictions_logged = 0
    pending_at_horizon = 0
    earliest_pending: str | None = None
    latest_pending: str | None = None
    distinct_tickers = 0
    try:
        all_preds = (
            _client.table("ai_predictions")
            .select("id,ticker,prediction_date")
            .gte("prediction_date", from_date)
            .limit(10000)
            .execute()
            .data
            or []
        )
        predictions_logged = len(all_preds)
        distinct_tickers = len({r.get("ticker") for r in all_preds if r.get("ticker")})
        # rows already have horizon outcomes (subset of `rows` from the view)
        scored_pred_ids = {r["id"] for r in rows if r.get("hit") is not None}
        pending_rows = [
            r for r in all_preds if r["id"] not in scored_pred_ids
        ]
        pending_at_horizon = len(pending_rows)
        if pending_rows:
            dates = sorted(r["prediction_date"] for r in pending_rows if r.get("prediction_date"))
            if dates:
                earliest_pending = dates[0]
                latest_pending = dates[-1]
    except Exception as e:
        logger.debug("accuracy_summary pending-stats fetch failed: %s", e)

    return {
        "horizon": horizon,
        "days": days,
        "filters": {"source": source, "impact_level": impact_level},
        **summary,
        "by_impact":    _group(rows, "impact_level"),
        "by_source":    _group(rows, "source"),
        "by_direction": _group(rows, "direction"),
        "by_catalyst":  _group(rows, "catalyst_type"),
        "predictions_logged":    predictions_logged,
        "pending_at_horizon":    pending_at_horizon,
        "distinct_tickers":      distinct_tickers,
        "earliest_pending_date": earliest_pending,
        "latest_pending_date":   latest_pending,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def recent_results(limit: int = 30, horizon: str = "1d") -> list[dict]:
    """Most recent (prediction, outcome) rows for the chosen horizon. Used for
    the "Recent calls" table on the Accuracy page so visitors can eyeball the
    actual claims and outcomes rather than just trust the aggregate.
    """
    if not _client:
        return []
    try:
        rows = (
            _client.table("prediction_results")
            .select("ticker,prediction_date,source,impact_level,direction,catalyst_type,reason,horizon,return_pct,hit,price_at_call,price_at_horizon")
            .eq("horizon", horizon)
            .not_.is_("hit", "null")
            .order("prediction_date", desc=True)
            .limit(limit)
            .execute()
            .data
        )
        return rows or []
    except Exception as e:
        logger.warning("recent_results fetch failed: %s", e)
        return []
