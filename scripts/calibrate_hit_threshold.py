#!/usr/bin/env python3
"""
calibrate_hit_threshold.py — re-derive HIT_THRESHOLD_SIGMA_K from real data.

WHY THIS EXISTS
---------------
`outcome_ledger.HIT_THRESHOLD_SIGMA_K` is the one number in the grading rule
that isn't forced by theory, and it is the easiest number in the codebase to
quietly corrupt: nudging it down makes the /accuracy hit rate go up, and
nothing would visibly break. This script is the check on that. Run it instead
of arguing about the value; if you change k, paste the output in the PR.

WHAT IT MEASURES
----------------
With a single threshold, 'positive'/'negative'/'neutral' split a fixed amount
of probability mass. Raise the bar to stop crediting directional noise and you
automatically hand the same free win to 'neutral'. So the question isn't "what
bar feels strict" but "what bar makes the three buckets equally hard for a
model with no skill at all".

For each candidate k it computes, over every real graded return:

  ZONE SHARES — where returns actually landed, i.e. exactly the hit rate a
    coin-flipper gets by always guessing that direction. The fair k is the one
    where the three are level (minimum spread).

  MODEL EDGE — real hit rate minus that bucket's no-skill share. This is the
    only honest read of whether the system predicts anything: a headline hit
    rate near the no-skill share means the number is measuring bucket
    composition, not skill.

  PER-STOCK FAIRNESS — the same no-skill rate computed separately for calm
    (bottom-third sigma) and volatile (top-third) names. A large gap means the
    bar is easier on some stocks than others, which is the flaw per-ticker
    sigma exists to remove.

Read-only. Touches no table. Needs SUPABASE_URL + SUPABASE_SERVICE_KEY, and
hits yfinance for price history.

Usage:
    python scripts/calibrate_hit_threshold.py
    python scripts/calibrate_hit_threshold.py --k-min 0.2 --k-max 0.6 --step 0.025
"""

from __future__ import annotations

import argparse
import math
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
    """PostgREST caps a response at 1000 rows whatever .limit() says."""
    out, step = [], 1000
    for off in range(0, 200_000, step):
        chunk = filt(client.table(table).select(select)).range(off, off + step - 1).execute().data or []
        out.extend(chunk)
        if len(chunk) < step:
            break
    return out


def load_graded(client) -> list[dict]:
    outs = _page(client, "prediction_outcomes", "prediction_id,horizon,return_pct,hit",
                 lambda q: q.not_.is_("hit", "null"))
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

    rows = []
    for pid, olist in by_pid.items():
        p = preds.get(pid)
        if not p or p["direction"] == "mixed":
            continue
        for o in olist:
            if o["return_pct"] is None:
                continue
            rows.append({"ticker": p["ticker"], "pdate": p["prediction_date"],
                         "direction": p["direction"], "horizon": o["horizon"],
                         "ret": float(o["return_pct"]), "hit": o["hit"]})
    return rows


def attach_sigma(rows: list[dict]) -> list[dict]:
    """Trailing sigma as of each prediction date. Same no-lookahead rule as
    outcome_ledger._trailing_sigma_pct — bars strictly up to the anchor."""
    start = date.fromisoformat(min(r["pdate"] for r in rows)) - timedelta(
        days=ol.SIGMA_HISTORY_LEAD_DAYS + 110)
    hist: dict[str, list[tuple[str, float]]] = {}
    for t in sorted({r["ticker"] for r in rows}):
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

    def sigma(ticker: str, pdate: str) -> float | None:
        prior = [c for d, c in (hist.get(ticker) or []) if d <= pdate]
        if len(prior) < ol.SIGMA_MIN_OBS + 1:
            return None
        w = prior[-(ol.SIGMA_LOOKBACK_TD + 1):]
        rets = [(w[i] - w[i - 1]) / w[i - 1] * 100.0 for i in range(1, len(w)) if w[i - 1]]
        return statistics.stdev(rets) if len(rets) >= ol.SIGMA_MIN_OBS else None

    cache: dict[tuple[str, str], float | None] = {}
    for r in rows:
        key = (r["ticker"], r["pdate"])
        if key not in cache:
            cache[key] = sigma(*key)
        r["sigma"] = cache[key]
    return [r for r in rows if r["sigma"] is not None]


def zone_shares(rows: list[dict], k: float, horizon: str) -> tuple[float, float, float]:
    sub = [r for r in rows if r["horizon"] == horizon]
    if not sub:
        return (0.0, 0.0, 0.0)
    td = ol.HORIZONS_TD.get(horizon, 1)
    up = dn = 0
    for r in sub:
        thr = k * r["sigma"] * math.sqrt(td)
        if r["ret"] >= thr:
            up += 1
        elif r["ret"] <= -thr:
            dn += 1
    n = len(sub)
    return (100 * up / n, 100 * dn / n, 100 * (n - up - dn) / n)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--k-min", type=float, default=0.20)
    ap.add_argument("--k-max", type=float, default=0.55)
    ap.add_argument("--step", type=float, default=0.025)
    args = ap.parse_args()

    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("ERROR: SUPABASE_URL / SUPABASE_SERVICE_KEY not set.", file=sys.stderr)
        return 2

    client = create_client(url, key)
    rows = load_graded(client)
    if not rows:
        print("No graded rows to calibrate against.")
        return 1
    print(f"graded rows: {len(rows)}  tickers: {len({r['ticker'] for r in rows})}")
    rows = attach_sigma(rows)
    print(f"with usable sigma: {len(rows)}")
    horizons = [h for h in ol.HORIZONS_TD if any(r["horizon"] == h for r in rows)]

    print("\n" + "=" * 78)
    print("ZONE SHARES — the hit rate a NO-SKILL guess gets in each bucket.")
    print("Level across up/dn/nt = a fair ruler. This is what fixes k.")
    print("=" * 78)
    best: tuple[float, float] | None = None
    k = args.k_min
    while k <= args.k_max + 1e-9:
        spreads, parts = [], []
        for h in horizons:
            up, dn, nt = zone_shares(rows, k, h)
            spreads.append(max(up, dn, nt) - min(up, dn, nt))
            parts.append(f"{h}: up{up:5.1f} dn{dn:5.1f} nt{nt:5.1f}")
        avg = sum(spreads) / len(spreads)
        mark = ""
        if best is None or avg < best[1]:
            best, mark = (k, avg), "  <-- fairest so far"
        print(f"  k={k:.3f}  " + "  ".join(parts) + f"   avg spread {avg:5.1f}pp{mark}")
        k = round(k + args.step, 6)

    print(f"\nFAIREST k = {best[0]:.3f}   (in code: HIT_THRESHOLD_SIGMA_K = "
          f"{ol.HIT_THRESHOLD_SIGMA_K})")
    if abs(best[0] - ol.HIT_THRESHOLD_SIGMA_K) > 0.05:
        print("  ^ drifted from the constant by >0.05 — worth a look, but do NOT "
              "retune k just because a hit rate looks low.")

    print("\n" + "=" * 78)
    print("MODEL EDGE at the configured k — hit rate minus the no-skill share.")
    print("Near zero means the headline number is bucket composition, not skill.")
    print("=" * 78)
    k = ol.HIT_THRESHOLD_SIGMA_K
    for h in horizons:
        up, dn, nt = zone_shares(rows, k, h)
        base = {"positive": up, "negative": dn, "neutral": nt}
        agg: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for r in (x for x in rows if x["horizon"] == h):
            a = agg[r["direction"]]
            a[0] += 1
            a[1] += 1 if ol._hit_rule(r["direction"], r["ret"], h, r["sigma"]) else 0
        tn = th = 0
        for d in ("positive", "negative", "neutral"):
            cnt, hits = agg[d]
            if not cnt:
                continue
            tn += cnt
            th += hits
            got = 100 * hits / cnt
            print(f"  {h} {d:9s} n={cnt:4d}  hit {got:5.1f}%  "
                  f"no-skill {base[d]:5.1f}%  edge {got - base[d]:+5.1f}pp")
        if tn:
            print(f"  {h} {'OVERALL':9s} n={tn:4d}  hit {100 * th / tn:5.1f}%")

    print("\n" + "=" * 78)
    print("PER-STOCK FAIRNESS — no-skill 'always positive' rate, calm vs volatile.")
    print("A big gap is the flaw per-ticker sigma exists to remove.")
    print("=" * 78)
    for h in horizons:
        sub = [r for r in rows if r["horizon"] == h]
        td = ol.HORIZONS_TD.get(h, 1)
        ss = sorted(r["sigma"] for r in sub)
        lo, hi = ss[len(ss) // 3], ss[2 * len(ss) // 3]
        calm = [r for r in sub if r["sigma"] <= lo]
        wild = [r for r in sub if r["sigma"] >= hi]

        def rate(group, thr_fn):
            return 100 * sum(1 for r in group if r["ret"] >= thr_fn(r)) / len(group)

        flat = 0.5 * math.sqrt(td)
        fc, fw = rate(calm, lambda r: flat), rate(wild, lambda r: flat)
        sc, sw = (rate(calm, lambda r: k * r["sigma"] * math.sqrt(td)),
                  rate(wild, lambda r: k * r["sigma"] * math.sqrt(td)))
        print(f"  {h}:  flat bar  calm {fc:5.1f}% wild {fw:5.1f}%  gap {abs(fc - fw):5.1f}pp"
              f"   ||  sigma bar  calm {sc:5.1f}% wild {sw:5.1f}%  gap {abs(sc - sw):5.1f}pp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
