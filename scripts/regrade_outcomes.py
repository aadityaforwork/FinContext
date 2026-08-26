#!/usr/bin/env python3
"""
regrade_outcomes.py — re-grade historical outcomes under the per-ticker rule.

WHY THIS IS A SCRIPT AND NOT A MIGRATION
----------------------------------------
Migration 012 re-graded the table in pure SQL, and could, because the old
threshold was a function of stored columns only (direction, return_pct,
horizon). The per-ticker rule broke that property: the bar depends on the
ticker's trailing volatility AS OF THE PREDICTION DATE, which lives in
yfinance, not Postgres. So re-grading needs network I/O and a real
no-lookahead sigma estimate per row — Python, not SQL.

WHAT IT CHANGES
---------------
For every graded (prediction, horizon) row it recomputes sigma as of the
prediction date, re-derives `hit`, and stores the bar actually used
(hit_threshold_pct / sigma_daily_pct / threshold_basis, migration 015).
`return_pct`, `price_at_horizon` and every prediction field are read-only
here — only the derived grade and the newly-recorded threshold are written.

WHY YOU SHOULD THINK BEFORE RUNNING IT
--------------------------------------
This rewrites the meaning of the whole public /accuracy page in one shot.
Rows that were hits become misses and vice versa. It is reversible in
principle (nothing source is destroyed, and 012's flat rule can be re-applied)
but there is no undo button here. DRY RUN IS THE DEFAULT — it prints the exact
before/after hit rates and changes nothing until you pass --apply.

A row whose sigma can't be estimated is graded on the flat fallback and marked
threshold_basis='flat' rather than skipped, so the table doesn't keep a
third, invisible grading regime.

Usage:
    python scripts/regrade_outcomes.py                 # dry run, prints impact
    python scripts/regrade_outcomes.py --apply         # actually write
    python scripts/regrade_outcomes.py --horizon 20d   # one horizon only
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
from collections import defaultdict
from datetime import date, timedelta

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, BACKEND)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(BACKEND, ".env"))

import yfinance as yf  # noqa: E402
from supabase import create_client  # noqa: E402

from app.nse_universe import resolve_yf_symbol  # noqa: E402
from app.services.outcomes import outcome_ledger as ol  # noqa: E402


def _page(client, table: str, select: str, filt):
    out, step = [], 1000
    for off in range(0, 200_000, step):
        chunk = filt(client.table(table).select(select)).range(off, off + step - 1).execute().data or []
        out.extend(chunk)
        if len(chunk) < step:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="Actually write. Without this it is a dry run.")
    ap.add_argument("--horizon", default=None, help="Limit to one horizon.")
    args = ap.parse_args()

    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("ERROR: SUPABASE_URL / SUPABASE_SERVICE_KEY not set.", file=sys.stderr)
        return 2
    client = create_client(url, key)

    outs = _page(client, "prediction_outcomes", "prediction_id,horizon,return_pct,hit",
                 lambda q: q.not_.is_("hit", "null"))
    if args.horizon:
        outs = [o for o in outs if o["horizon"] == args.horizon]
    by_pid: dict[str, list[dict]] = defaultdict(list)
    for o in outs:
        by_pid[o["prediction_id"]].append(o)

    preds: dict[str, dict] = {}
    pids = list(by_pid)
    for i in range(0, len(pids), 300):
        for p in (client.table("ai_predictions")
                  .select("id,ticker,prediction_date,direction")
                  .in_("id", pids[i:i + 300]).execute().data or []):
            preds[p["id"]] = p

    work = []
    for pid, olist in by_pid.items():
        p = preds.get(pid)
        if not p or p["direction"] == "mixed":
            continue  # scored NULL by design; must stay NULL
        for o in olist:
            if o["return_pct"] is None:
                continue
            work.append({"pid": pid, "ticker": p["ticker"], "pdate": p["prediction_date"],
                         "direction": p["direction"], "horizon": o["horizon"],
                         "ret": float(o["return_pct"]), "old_hit": o["hit"]})
    if not work:
        print("Nothing to re-grade.")
        return 0
    print(f"rows to re-grade: {len(work)}  tickers: {len({w['ticker'] for w in work})}")

    start = date.fromisoformat(min(w["pdate"] for w in work)) - timedelta(
        days=ol.SIGMA_HISTORY_LEAD_DAYS + 110)
    hist: dict[str, list[tuple[str, float]]] = {}
    for t in sorted({w["ticker"] for w in work}):
        sym = resolve_yf_symbol(t)
        if not sym:
            hist[t] = []
            continue
        try:
            h = yf.Ticker(sym).history(start=start.isoformat(), auto_adjust=False)
            hist[t] = [] if h is None or h.empty else [
                (i.date().isoformat(), float(r["Close"])) for i, r in h.iterrows()]
        except Exception as e:  # noqa: BLE001
            print(f"  !! {t}: {e}", file=sys.stderr)
            hist[t] = []

    def sigma_for(ticker: str, pdate: str) -> float | None:
        """Bars up to and including the prediction's own close — never past it."""
        prior = [c for d, c in (hist.get(ticker) or []) if d <= pdate]
        if len(prior) < ol.SIGMA_MIN_OBS + 1:
            return None
        w = prior[-(ol.SIGMA_LOOKBACK_TD + 1):]
        rets = [(w[i] - w[i - 1]) / w[i - 1] * 100.0 for i in range(1, len(w)) if w[i - 1]]
        return statistics.stdev(rets) if len(rets) >= ol.SIGMA_MIN_OBS else None

    cache: dict[tuple[str, str], float | None] = {}
    updates, flipped, no_sigma = [], 0, 0
    stats: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])  # n, old, new
    for w in work:
        key = (w["ticker"], w["pdate"])
        if key not in cache:
            cache[key] = sigma_for(*key)
        sigma = cache[key]
        if sigma is None:
            no_sigma += 1
        new_hit = ol._hit_rule(w["direction"], w["ret"], w["horizon"], sigma)
        if new_hit != w["old_hit"]:
            flipped += 1
        s = stats[(w["horizon"], w["direction"])]
        s[0] += 1
        s[1] += 1 if w["old_hit"] else 0
        s[2] += 1 if new_hit else 0
        updates.append({
            "prediction_id": w["pid"], "horizon": w["horizon"],
            "return_pct": w["ret"], "hit": new_hit,
            "hit_threshold_pct": ol.hit_threshold_pct(w["horizon"], sigma),
            "sigma_daily_pct": round(sigma, 4) if sigma is not None else None,
            "threshold_basis": "sigma" if sigma is not None else "flat",
        })

    print(f"sigma unavailable (graded on flat fallback): {no_sigma}")
    print(f"grades that FLIP: {flipped} / {len(work)}\n")
    print(f"{'horizon':8s} {'direction':10s} {'n':>5s} {'old':>7s} {'new':>7s}  delta")
    for (h, d) in sorted(stats):
        n, old, new = stats[(h, d)]
        print(f"{h:8s} {d:10s} {n:5d} {100 * old / n:6.1f}% {100 * new / n:6.1f}%  "
              f"{100 * (new - old) / n:+5.1f}pp")
    for h in sorted({k[0] for k in stats}):
        n = sum(stats[k][0] for k in stats if k[0] == h)
        old = sum(stats[k][1] for k in stats if k[0] == h)
        new = sum(stats[k][2] for k in stats if k[0] == h)
        print(f"{h:8s} {'ALL':10s} {n:5d} {100 * old / n:6.1f}% {100 * new / n:6.1f}%  "
              f"{100 * (new - old) / n:+5.1f}pp")

    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to commit these grades.")
        return 0

    written = 0
    for i in range(0, len(updates), 500):
        chunk = updates[i:i + 500]
        try:
            client.table("prediction_outcomes").upsert(
                chunk, on_conflict="prediction_id,horizon").execute()
            written += len(chunk)
        except Exception as e:  # noqa: BLE001
            print(f"  !! chunk {i} failed: {e}", file=sys.stderr)
    print(f"\nwrote {written}/{len(updates)} rows.")
    return 0 if written == len(updates) else 1


if __name__ == "__main__":
    raise SystemExit(main())
