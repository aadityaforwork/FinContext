#!/usr/bin/env python3
"""Trigger the independent grounding-contract monitor.

Run this before ``run_prompt_drafter.py --action run-pending`` so any new
grounding alerts are already in their queue. This job never edits a prompt.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default=os.getenv("FINCONTEXT_API_BASE"))
    parser.add_argument("--admin-token", default=os.getenv("FINCONTEXT_ADMIN_TOKEN"))
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    if not args.api_base or not args.admin_token:
        print("ERROR: --api-base and --admin-token are required.", file=sys.stderr)
        return 2

    url = args.api_base.rstrip("/") + "/api/grounding-monitor/run-daily"
    request = Request(
        url,
        method="POST",
        data=b"",
        headers={"X-Admin-Token": args.admin_token, "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=args.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, json.JSONDecodeError) as exc:
        print(f"Grounding monitor failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(data, indent=2))
    return (
        1
        if any(
            result.get("action") in {"error", "alert_send_failed"}
            for prompt_results in data.values()
            for result in prompt_results.values()
        )
        else 0
    )


if __name__ == "__main__":
    sys.exit(main())
