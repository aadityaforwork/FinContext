#!/usr/bin/env python3
"""
run_accuracy_monitor.py — manually trigger the daily accuracy-drift monitor.

Hits POST /api/accuracy-monitor/run-daily on the FinContext backend so the
path-back leg 3c job compares each monitored source's recent market-graded
hit rate against its own trailing baseline and pushes a Telegram alert to
the operator if (and only if) accuracy has dropped past both the
sample-size and effect-size thresholds. Idempotent — safe to re-run any
time. NEVER writes a prompt or a Langfuse label — see
backend/app/services/accuracy_monitor.py's module docstring.

Usage (env vars):
    export FINCONTEXT_API_BASE=https://your-backend.onrender.com
    export FINCONTEXT_ADMIN_TOKEN=...
    python scripts/run_accuracy_monitor.py

Usage (CLI flags):
    python scripts/run_accuracy_monitor.py \\
        --api-base https://your-backend.onrender.com \\
        --admin-token ...

Designed to be run by:
  - a developer locally (one-off, to check what the monitor would decide)
  - cron-job.org once a day, same schedule family as compute_outcomes.py /
    run_prompt_monitor.py (see scripts/README.md) — run this AFTER
    compute_outcomes.py so the outcome ledger has today's graded rows before
    this job reads them.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--api-base", default=os.getenv("FINCONTEXT_API_BASE"),
        help="Backend URL, e.g. https://api.fincontext.app (or set FINCONTEXT_API_BASE)",
    )
    parser.add_argument(
        "--admin-token", default=os.getenv("FINCONTEXT_ADMIN_TOKEN"),
        help="Admin token matching ADMIN_TOKEN on the server (or set FINCONTEXT_ADMIN_TOKEN)",
    )
    parser.add_argument(
        "--timeout", type=int, default=120,
        help="Request timeout in seconds (default: 120)",
    )
    args = parser.parse_args()

    if not args.api_base or not args.admin_token:
        print(
            "ERROR: --api-base and --admin-token are required "
            "(or set FINCONTEXT_API_BASE / FINCONTEXT_ADMIN_TOKEN).",
            file=sys.stderr,
        )
        return 2

    url = args.api_base.rstrip("/") + "/api/accuracy-monitor/run-daily"
    req = Request(
        url, method="POST",
        headers={"X-Admin-Token": args.admin_token, "Content-Type": "application/json"},
        data=b"",
    )

    print(f"POST {url}")
    try:
        with urlopen(req, timeout=args.timeout) as resp:
            body = resp.read().decode("utf-8")
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code} {e.reason}", file=sys.stderr)
        print(body, file=sys.stderr)
        return 1
    except URLError as e:
        print(f"Network error: {e.reason}", file=sys.stderr)
        return 1

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        print("Response was not JSON:", file=sys.stderr)
        print(body, file=sys.stderr)
        return 1

    print(json.dumps(data, indent=2))

    had_error = False
    for source, result in data.items():
        action = result.get("action")
        reason = result.get("reason")
        print(f"\n{source}: {action} — {reason}")
        if action in ("alerted", "alert_send_failed"):
            print(f"  drop_pp={result.get('drop_pp')}  "
                  f"baseline={result.get('baseline_hit_rate_pct')}% (n={result.get('baseline_n')}) "
                  f"-> recent={result.get('recent_hit_rate_pct')}% (n={result.get('recent_n')})")
        if action in ("error", "alert_send_failed"):
            had_error = True

    return 1 if had_error else 0


if __name__ == "__main__":
    sys.exit(main())
