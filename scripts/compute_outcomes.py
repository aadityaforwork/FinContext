#!/usr/bin/env python3
"""
compute_outcomes.py — manually trigger the daily outcome-computation pass.

Hits POST /api/outcomes/compute-daily on the FinContext backend so the
outcome ledger fills in return + hit values for every (prediction, horizon)
pair whose horizon has fully elapsed. Idempotent — safe to re-run any time.

Usage (env vars):
    export FINCONTEXT_API_BASE=https://your-backend.onrender.com
    export FINCONTEXT_ADMIN_TOKEN=...
    python scripts/compute_outcomes.py

Usage (CLI flags):
    python scripts/compute_outcomes.py \\
        --api-base https://your-backend.onrender.com \\
        --admin-token ...

Designed to be run by:
  - a developer locally (one-off, after a deploy or to backfill outcomes)
  - cron-job.org once a day at ~11:00 UTC (4:30 PM IST) — see scripts/README.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


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
        "--timeout", type=int, default=180,
        help="Request timeout in seconds (default: 180 — generous for cold Render workers)",
    )
    args = parser.parse_args()

    if not args.api_base or not args.admin_token:
        print(
            "ERROR: --api-base and --admin-token are required "
            "(or set FINCONTEXT_API_BASE / FINCONTEXT_ADMIN_TOKEN).",
            file=sys.stderr,
        )
        return 2

    url = args.api_base.rstrip("/") + "/api/outcomes/compute-daily"
    req = Request(
        url,
        method="POST",
        headers={
            "X-Admin-Token": args.admin_token,
            "Content-Type": "application/json",
        },
        data=b"",
    )

    print(f"POST {url}")
    try:
        with urlopen(req, timeout=args.timeout) as resp:
            body = resp.read().decode("utf-8")
            status = resp.status
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
        print(f"HTTP {status} but response was not JSON:", file=sys.stderr)
        print(body, file=sys.stderr)
        return 1

    print(json.dumps(data, indent=2))
    if isinstance(data, dict) and data.get("error"):
        print(f"\nServer reported error: {data['error']}", file=sys.stderr)
        return 1

    processed = data.get("processed", 0)
    written = data.get("written", 0)
    skipped = data.get("skipped", 0)
    errors = data.get("errors", 0)
    by_horizon = data.get("by_horizon", {})

    print(
        f"\nSummary: {processed} pairs processed · "
        f"{written} written · {skipped} skipped (not enough trading days yet) · "
        f"{errors} errors"
    )
    if by_horizon:
        print("By horizon: " + ", ".join(f"{h}={n}" for h, n in by_horizon.items()))

    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
