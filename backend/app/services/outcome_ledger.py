"""
Outcome Ledger
==============
Records every forward-looking AI prediction the system makes (Tomorrow
per-holding watch items + News Impact items) and computes whether the
predicted direction matched the actual price move 1d / 5d / 20d later.

Backed by Supabase tables `ai_predictions` + `prediction_outcomes`
(migration 004_outcome_ledger.sql). Reads/writes via the service-role key.

Also owns `prompt_call_log` (migration 008_prompt_call_log.sql) — a
call-grained (not prediction-grained) log of every Langfuse-managed-prompt
call, feeding prompt_monitor.py's Phase 3 online comparison. Lives in this
module rather than a new one: same Supabase client, same best-effort
posture, same "ledger of AI-call telemetry" theme as everything else here —
see log_call_metrics()'s docstring for why it can't just be derived from
ai_predictions.

Also owns `accuracy_alert_log` (migration 009_accuracy_alert_log.sql) — one
row per alert accuracy_monitor.py actually fires (not every evaluation, just
the ones that crossed the threshold), used both as an audit trail and to
drive that module's alert cooldown. Same reasoning for living here as
prompt_call_log above.

Also owns `miss_fixtures` (migration 010_miss_fixtures.sql) — permanent eval
fixtures converted from real market-graded misses, feeding miss_fixtures.py
(path-back leg 3d). `prompt_call_log.context_snapshot` (same migration) is
the private stash of exact-context-at-call-time these fixtures are built
from — see log_call_metrics' docstring for why that snapshot can never live
on ai_predictions instead (that table is publicly readable).

Public functions:
    log_predictions(items)              — bulk-upsert prediction rows
    compute_pending_outcomes()          — fill in outcomes for due predictions
    accuracy_summary(...)               — aggregate hit-rate breakdowns
    recent_results(limit)               — recent (prediction, outcome) rows
    scored_rows(horizon, days)          — raw graded rows, feeds track_record.py + accuracy_monitor.py
    log_call_metrics(...)               — log one LLM call's deterministic metrics (+ optional context snapshot)
    call_metrics_rows(prompt_name, days) — raw metric rows for a prompt
    call_context(call_id)               — {prompt_name, context_snapshot} for one logged call
    log_accuracy_alert(...)             — log one fired accuracy-drift alert
    last_accuracy_alert(source, days)   — most recent alert for a source, for cooldown
    recent_accuracy_alerts(days)        — every alert in a window, feeds prompt_drafter.py
    graded_misses(horizon, days)        — market-graded misses, feeds miss_fixtures.py
    log_miss_fixture(...)               — convert one miss into a permanent eval fixture
    miss_fixture_rows(prompt_name, limit) — stored miss fixtures for a prompt

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


def scored_rows(horizon: str = "1d", days: int = 90) -> list[dict]:
    """Raw {source, catalyst_type, hit, prediction_date} rows for the given
    horizon — feeds track_record.py's calibration segments and
    accuracy_monitor.py's drift check. Deliberately minimal (no aggregation,
    no impact_level) so it stays cheap to call from a cache refresh.
    `prediction_date` is only consumed by accuracy_monitor.py (track_record.py
    ignores the extra key) — kept in one function rather than two nearly-
    identical queries. Excludes ungraded/pending rows (hit IS NULL) via the
    view join. Best-effort — returns [] on any failure, never raises.
    """
    if not _client:
        return []
    today = datetime.now(timezone.utc).date()
    from_date = (today - timedelta(days=days)).isoformat()
    try:
        rows = (
            _client.table("prediction_results")
            .select("source,catalyst_type,hit,prediction_date")
            .eq("horizon", horizon)
            .gte("prediction_date", from_date)
            .not_.is_("hit", "null")
            .limit(10000)
            .execute()
            .data
            or []
        )
        return rows
    except Exception as e:
        logger.warning("scored_rows fetch failed: %s", e)
        return []


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


# ---------------------------------------------------------------------------
# Prompt call log — path-back leg 3b, Phase 3 (prompt_monitor.py). Backed by
# `prompt_call_log` (migration 008_prompt_call_log.sql).
# ---------------------------------------------------------------------------
def log_call_metrics(
    prompt_name: str,
    prompt_version: int | None,
    prompt_source: str,
    *,
    call_id: str | None = None,
    context_snapshot: dict | None = None,
    confidence: str | None = None,
    data_gaps_count: int | None = None,
    parse_error: bool = False,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    duration_ms: float | None = None,
) -> bool:
    """Best-effort log of one LLM call's deterministic metrics.

    One row per ai_client.generate_grounded_json() call — deliberately NOT
    derived from ai_predictions rows, for two reasons: (1) a single call can
    produce many prediction rows (e.g. 15 per_holding items from one
    tomorrow-watch call), so averaging over prediction rows would
    over-weight calls that happened to produce more items; (2) a call whose
    JSON fails to parse produces ZERO prediction rows (log_predictions is
    never even called), so ai_predictions structurally can't represent
    "how often does this prompt fail to produce valid output" — exactly
    the schema_validation_failure_rate prompt_monitor.py needs. This table
    makes every attempted call visible, success or failure.

    `call_id` (optional): if given, used as this row's primary key instead
    of letting Postgres generate one — lets the caller (portfolio_
    intelligence.py) stamp the SAME id into ai_predictions.metadata.call_id
    as a join key, without a second round trip to read the generated id
    back. `context_snapshot` (optional): the exact CONTEXT dict passed to
    generate_grounded_json for this call — feeds miss_fixtures.py's
    replay-and-check fixtures. Deliberately stored HERE, never in
    ai_predictions.metadata: ai_predictions has a public "anon select" RLS
    policy (migration 004 — the Accuracy page is intentionally public), so
    a real user's portfolio/watchlist context must never land there. See
    AGENTS.md rule 9.

    Never raises; returns False (no-op) if the ledger is unavailable or the
    insert fails — same posture as log_predictions().
    """
    if not _client:
        return False
    try:
        row = {
            "prompt_name": prompt_name,
            "prompt_version": prompt_version,
            "prompt_source": prompt_source,
            "context_snapshot": context_snapshot,
            "confidence": confidence,
            "data_gaps_count": data_gaps_count,
            "parse_error": bool(parse_error),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "duration_ms": duration_ms,
        }
        if call_id:
            row["id"] = call_id
        _client.table("prompt_call_log").insert(row).execute()
        return True
    except Exception as e:
        logger.warning("log_call_metrics failed: %s", e)
        return False


def call_metrics_rows(prompt_name: str, days: int = 30) -> list[dict]:
    """Raw per-call metric rows for `prompt_name` in the last `days` days,
    newest first. Feeds prompt_monitor.py's version comparison. Best-effort
    — returns [] on any failure, never raises.
    """
    if not _client:
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        rows = (
            _client.table("prompt_call_log")
            .select(
                "prompt_version,prompt_source,confidence,data_gaps_count,"
                "parse_error,tokens_in,tokens_out,duration_ms,created_at"
            )
            .eq("prompt_name", prompt_name)
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .limit(5000)
            .execute()
            .data
            or []
        )
        return rows
    except Exception as e:
        logger.warning("call_metrics_rows fetch failed: %s", e)
        return []


def call_context(call_id: str) -> dict | None:
    """The stored {prompt_name, context_snapshot} for one prompt_call_log
    row by id — `call_id` is the same value the router stamped into both
    that row and ai_predictions.metadata.call_id (see log_call_metrics'
    docstring). Feeds miss_fixtures.py: given a graded miss, this is how it
    finds the exact context that was live when the call was made. None if
    not found, `call_id` is falsy, or the client is unavailable.
    Best-effort — never raises.
    """
    if not _client or not call_id:
        return None
    try:
        rows = (
            _client.table("prompt_call_log")
            .select("prompt_name,context_snapshot")
            .eq("id", call_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        return rows[0] if rows else None
    except Exception as e:
        logger.warning("call_context fetch failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Accuracy alert log — path-back leg 3c (accuracy_monitor.py). Backed by
# `accuracy_alert_log` (migration 009_accuracy_alert_log.sql).
# ---------------------------------------------------------------------------
def log_accuracy_alert(
    source: str,
    prompt_name: str | None,
    *,
    recent_n: int,
    recent_hit_rate_pct: float,
    baseline_n: int,
    baseline_hit_rate_pct: float,
    drop_pp: float,
    message: str,
) -> bool:
    """Best-effort log of one fired accuracy-drift alert. Only called when
    accuracy_monitor.py actually crosses its threshold — not every daily
    evaluation, which would make this table as noisy as the logs. Two jobs:
    a permanent audit trail, and the read side (last_accuracy_alert) is what
    lets accuracy_monitor.py avoid re-alerting on the same still-degraded
    segment every single day. Never raises; returns False on failure or if
    the client is unavailable — same posture as log_call_metrics().
    """
    if not _client:
        return False
    try:
        _client.table("accuracy_alert_log").insert({
            "source": source,
            "prompt_name": prompt_name,
            "recent_n": recent_n,
            "recent_hit_rate_pct": recent_hit_rate_pct,
            "baseline_n": baseline_n,
            "baseline_hit_rate_pct": baseline_hit_rate_pct,
            "drop_pp": drop_pp,
            "message": message,
        }).execute()
        return True
    except Exception as e:
        logger.warning("log_accuracy_alert failed: %s", e)
        return False


def recent_accuracy_alerts(days: int = 14) -> list[dict]:
    """Every `accuracy_alert_log` row in the last `days` days, newest first
    — feeds prompt_drafter.py's run_pending_drafts(), which turns a fired
    accuracy-drift alert into a draft-and-test attempt at fixing the
    underlying prompt (path-back leg 3e — the piece last_accuracy_alert
    above doesn't cover, since that one only ever returns the SINGLE most
    recent row for one known source, not "every alert in this window" across
    all sources). Best-effort — returns [] on any failure, never raises.
    """
    if not _client:
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        rows = (
            _client.table("accuracy_alert_log")
            .select("source,prompt_name,message,drop_pp,created_at")
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .limit(200)
            .execute()
            .data
            or []
        )
        return rows
    except Exception as e:
        logger.warning("recent_accuracy_alerts fetch failed: %s", e)
        return []


def last_accuracy_alert(source: str, days: int = 7) -> dict | None:
    """Most recent `accuracy_alert_log` row for `source` within the last
    `days` days, or None if there isn't one (including when the client is
    unavailable or the query fails — best-effort, never raises). Feeds
    accuracy_monitor.py's alert cooldown so a segment that's still degraded
    tomorrow doesn't fire a second Telegram message tomorrow too.
    """
    if not _client:
        return None
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        rows = (
            _client.table("accuracy_alert_log")
            .select("created_at")
            .eq("source", source)
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
            .data
            or []
        )
        return rows[0] if rows else None
    except Exception as e:
        logger.warning("last_accuracy_alert fetch failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Miss fixtures — path-back leg 3d (miss_fixtures.py). Backed by
# `miss_fixtures` (migration 010_miss_fixtures.sql).
# ---------------------------------------------------------------------------
def graded_misses(horizon: str = "1d", days: int = 30) -> list[dict]:
    """Every prediction graded as a miss (hit=False, direction != 'mixed')
    at `horizon` in the last `days` days — one dict per miss:
    {prediction_id, ticker, prediction_date, source, catalyst_type,
    direction, reason, return_pct, metadata}. `metadata` carries `call_id`
    when the router set one at log time (see portfolio_intelligence.py's
    _tomorrow_call_id / _news_call_id) — miss_fixtures.py uses it via
    call_context() to find the exact context that was live for that call.
    Queries ai_predictions/prediction_outcomes directly (not the public
    prediction_results view) purely because the view doesn't select
    `metadata` — nothing here is more sensitive than what the view already
    exposes. Best-effort — returns [] on any failure, never raises.
    """
    if not _client:
        return []
    today = datetime.now(timezone.utc).date()
    from_date = (today - timedelta(days=days)).isoformat()
    try:
        outcome_rows = (
            _client.table("prediction_outcomes")
            .select("prediction_id,return_pct")
            .eq("horizon", horizon)
            .eq("hit", False)
            .not_.is_("return_pct", "null")
            .limit(2000)
            .execute()
            .data
            or []
        )
        if not outcome_rows:
            return []
        return_by_id = {r["prediction_id"]: r["return_pct"] for r in outcome_rows}
        pred_ids = list(return_by_id.keys())

        preds: list[dict] = []
        for i in range(0, len(pred_ids), 500):
            chunk = pred_ids[i:i + 500]
            r = (
                _client.table("ai_predictions")
                .select("id,ticker,prediction_date,source,catalyst_type,direction,reason,metadata")
                .in_("id", chunk)
                .neq("direction", "mixed")
                .gte("prediction_date", from_date)
                .execute()
            )
            preds.extend(r.data or [])

        return [
            {
                "prediction_id": p["id"], "ticker": p["ticker"],
                "prediction_date": p["prediction_date"], "source": p["source"],
                "catalyst_type": p.get("catalyst_type"), "direction": p["direction"],
                "reason": p.get("reason"), "metadata": p.get("metadata") or {},
                "return_pct": return_by_id.get(p["id"]),
            }
            for p in preds
        ]
    except Exception as e:
        logger.warning("graded_misses fetch failed: %s", e)
        return []


def log_miss_fixture(
    prediction_id: str,
    prompt_name: str,
    *,
    ticker: str,
    prediction_date: str,
    catalyst_type: str | None,
    original_direction: str,
    expected_direction: str,
    reason: str | None,
    return_pct: float,
    context_snapshot: dict,
) -> bool:
    """Best-effort write of one converted miss fixture. `prediction_id` is
    UNIQUE on the table — a second attempt to convert the same prediction
    (the daily job re-scanning its lookback window) hits a duplicate-key
    error, which is treated as an EXPECTED no-op (already converted), not a
    failure, and logged at debug rather than warning. Never raises; returns
    False on any failure including the expected duplicate case.
    """
    if not _client:
        return False
    try:
        _client.table("miss_fixtures").insert({
            "prediction_id": prediction_id,
            "prompt_name": prompt_name,
            "ticker": ticker,
            "prediction_date": prediction_date,
            "catalyst_type": catalyst_type,
            "original_direction": original_direction,
            "expected_direction": expected_direction,
            "reason": reason,
            "return_pct": return_pct,
            "context_snapshot": context_snapshot,
        }).execute()
        return True
    except Exception as e:
        if "duplicate key" in str(e).lower() or "23505" in str(e):
            logger.debug("log_miss_fixture: prediction %s already has a fixture", prediction_id)
        else:
            logger.warning("log_miss_fixture failed: %s", e)
        return False


def miss_fixture_rows(prompt_name: str, limit: int = 200) -> list[dict]:
    """Stored miss fixtures for `prompt_name`, newest first — feeds
    miss_fixtures.load_miss_fixture_cases(), which turns each row into an
    eval_runner.EvalCase. Best-effort — returns [] on any failure, never
    raises.
    """
    if not _client:
        return []
    try:
        rows = (
            _client.table("miss_fixtures")
            .select(
                "id,prediction_id,ticker,prediction_date,catalyst_type,"
                "original_direction,expected_direction,reason,return_pct,"
                "context_snapshot,created_at"
            )
            .eq("prompt_name", prompt_name)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
            .data
            or []
        )
        return rows
    except Exception as e:
        logger.warning("miss_fixture_rows fetch failed: %s", e)
        return []
