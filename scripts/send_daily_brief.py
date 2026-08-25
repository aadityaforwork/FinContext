#!/usr/bin/env python3
"""
send_daily_brief.py — fire the morning brief for every subscribed user.

Hits the FinContext backend, which iterates every subscriber for the chosen
channel, builds their personalized P&L + movers + policy headlines brief, and
pushes it out.

  --channel telegram   POST /api/telegram/send-daily-brief  (telegram_links)
  --channel email      POST /api/brief/send-daily-email     (email_brief_subs)

Idempotent — safe to re-run any time.

Usage (env vars):
    export FINCONTEXT_API_BASE=https://your-backend.onrender.com
    export FINCONTEXT_ADMIN_TOKEN=...
    python scripts/send_daily_brief.py                    # telegram
    python scripts/send_daily_brief.py --channel email    # email

Schedule:
    cron-job.org → "0 3 * * 1-5"  (3:00 UTC = 8:30 AM IST, Mon-Fri only)
    One cronjob per channel, both hitting the URLs above directly.
    See scripts/README.md → "Telegram bot daily brief" and "Daily brief email"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

CHANNEL_PATHS = {
    "telegram": "/api/telegram/send-daily-brief",
    "email": "/api/brief/send-daily-email",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--channel", choices=sorted(CHANNEL_PATHS), default="telegram",
        help="Which channel to fire. Default telegram.",
    )
    parser.add_argument(
        "--api-base", default=os.getenv("FINCONTEXT_API_BASE"),
        help="Backend URL (or set FINCONTEXT_API_BASE)",
    )
    parser.add_argument(
        "--admin-token", default=os.getenv("FINCONTEXT_ADMIN_TOKEN"),
        help="Admin token matching ADMIN_TOKEN on the server (or set FINCONTEXT_ADMIN_TOKEN)",
    )
    parser.add_argument(
        "--only-user-id", default=None,
        help="Send to just this user id. Email channel only, for testing.",
    )
    parser.add_argument(
        "--timeout", type=int, default=240,
        help="Request timeout (seconds). Default 240 — generous for cold Render workers + many users",
    )
    args = parser.parse_args()

    if not args.api_base or not args.admin_token:
        print(
            "ERROR: --api-base and --admin-token are required "
            "(or set FINCONTEXT_API_BASE / FINCONTEXT_ADMIN_TOKEN).",
            file=sys.stderr,
        )
        return 2

    if args.only_user_id and args.channel != "email":
        print("ERROR: --only-user-id is only supported on --channel email.", file=sys.stderr)
        return 2

    url = args.api_base.rstrip("/") + CHANNEL_PATHS[args.channel]
    if args.only_user_id:
        url += f"?only_user_id={args.only_user_id}"
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

    targets = data.get("targets", 0)
    sent = data.get("sent", 0)
    failed = data.get("failed", 0)
    skipped = data.get("skipped_no_holdings", 0)

    print(
        f"\n{args.channel} summary: {sent}/{targets} sent · "
        f"{skipped} skipped (no holdings) · {failed} failed"
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
