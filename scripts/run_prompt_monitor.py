#!/usr/bin/env python3
"""
run_prompt_monitor.py — manually trigger the daily prompt-version monitor.

Hits POST /api/prompt-monitor/run-daily on the FinContext backend so the
Phase 3 online monitor compares each monitored prompt's live version against
the version that was live before it, and reverts the `production` label if
(and only if) metrics have degraded past both the sample-size and
effect-size thresholds. Idempotent — safe to re-run any time. NEVER
promotes — see backend/app/services/prompt_monitor.py's module docstring.

Usage (env vars):
    export FINCONTEXT_API_BASE=https://your-backend.onrender.com
    export FINCONTEXT_ADMIN_TOKEN=...
    python scripts/run_prompt_monitor.py

Usage (CLI flags):
    python scripts/run_prompt_monitor.py \\
        --api-base https://your-backend.onrender.com \\
        --admin-token ...

Designed to be run by:
  - a developer locally (one-off, to check what the monitor would decide)
  - cron-job.org once a day, same schedule family as compute_outcomes.py
    (see scripts/README.md) — run this AFTER compute_outcomes.py so outcome
    data (if ever wired into these metrics) is fresh, though today's
    metrics come entirely from prompt_call_log, independent of the outcome
    ledger's daily scoring pass.
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

    url = args.api_base.rstrip("/") + "/api/prompt-monitor/run-daily"
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
    for prompt_name, result in data.items():
        action = result.get("action")
        reason = result.get("reason")
        print(f"\n{prompt_name}: {action} — {reason}")
        if action in ("reverted", "revert_failed"):
            print(f"  degraded_metrics={result.get('degraded_metrics')}  "
                  f"v{result.get('current_version')} -> v{result.get('previous_version')}")
        if action in ("error", "revert_failed"):
            had_error = True

    return 1 if had_error else 0


if __name__ == "__main__":
    sys.exit(main())
