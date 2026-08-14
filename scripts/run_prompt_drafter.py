#!/usr/bin/env python3
"""
run_prompt_drafter.py — manually trigger the prompt-drafter's two jobs.

Path-back leg 3e: hits both admin-token endpoints on the FinContext backend.

  --action run-pending     POST /api/prompt-drafter/run-pending
                            Scan accuracy_monitor.py's alert log for newly
                            flagged prompts and start a draft-test-approve
                            run for each one not already in flight.

  --action check-approvals POST /api/prompt-drafter/check-approvals
                            For every run paused awaiting a human, check
                            whether the Langfuse `production` label has
                            been moved to that run's candidate version and,
                            if so, resume + close the loop.

Both are idempotent — safe to re-run any time.

Usage (env vars):
    export FINCONTEXT_API_BASE=https://your-backend.onrender.com
    export FINCONTEXT_ADMIN_TOKEN=...
    python scripts/run_prompt_drafter.py --action run-pending
    python scripts/run_prompt_drafter.py --action check-approvals
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ACTIONS = {
    "run-pending": "/api/prompt-drafter/run-pending",
    "check-approvals": "/api/prompt-drafter/check-approvals",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--action", required=True, choices=sorted(ACTIONS))
    parser.add_argument(
        "--api-base", default=os.getenv("FINCONTEXT_API_BASE"),
        help="Backend URL, e.g. https://api.fincontext.app (or set FINCONTEXT_API_BASE)",
    )
    parser.add_argument(
        "--admin-token", default=os.getenv("FINCONTEXT_ADMIN_TOKEN"),
        help="Admin token matching ADMIN_TOKEN on the server (or set FINCONTEXT_ADMIN_TOKEN)",
    )
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    if not args.api_base or not args.admin_token:
        print(
            "ERROR: --api-base and --admin-token are required "
            "(or set FINCONTEXT_API_BASE / FINCONTEXT_ADMIN_TOKEN).",
            file=sys.stderr,
        )
        return 2

    url = args.api_base.rstrip("/") + ACTIONS[args.action]
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
    return 1 if data.get("errors") else 0


if __name__ == "__main__":
    sys.exit(main())
