"""
Brief email Router
==================
The email twin of the Telegram daily brief. Same payload, same admin-token
cron trigger, different transport.

  AUTHED USER (frontend -> us)
      POST   /api/brief/email-subscribe   opt in, snapshots the account email
      GET    /api/brief/email-status      am I subscribed?
      DELETE /api/brief/email-subscribe   opt out
      Auth: Bearer <supabase_access_token>

  PUBLIC (mail client -> us)
      GET|POST /api/brief/email-unsubscribe?token=...
      Auth: the unguessable per-subscriber token itself

  ADMIN (cron -> us)
      POST /api/brief/send-daily-email
      Auth: X-Admin-Token header

Subscriptions live in `email_brief_subs` rather than piggybacking on
`telegram_links`, so a user can take either channel without the other.
"""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from supabase import create_client

from app.routers.telegram import build_user_brief, verify_supabase_user
from app.services import email_sender

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/brief", tags=["brief-email"])

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")
WEB_APP_URL = os.getenv("WEB_APP_URL", "https://fincontext.app")

# This backend's own public origin, needed to build unsubscribe links that
# work from a mail client. Unset means we send without an unsubscribe link.
PUBLIC_API_BASE = os.getenv("PUBLIC_API_BASE")

_sb = None
if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    try:
        _sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        logger.info("Brief email router: supabase service client initialized")
    except Exception as e:
        logger.error("Brief email router: supabase init failed: %s", e)


def _require_sb():
    if not _sb:
        raise HTTPException(status_code=503, detail="Supabase not configured.")
    return _sb


def _check_admin(token: str | None) -> None:
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="ADMIN_TOKEN not configured.")
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid admin token.")


def _unsubscribe_url(token: str | None) -> str | None:
    if not token or not PUBLIC_API_BASE:
        return None
    return f"{PUBLIC_API_BASE.rstrip('/')}/api/brief/email-unsubscribe?token={token}"


def _set_enabled_by_token(token: str) -> bool:
    """Flip a subscription off by its unsubscribe token. True if one matched."""
    sb = _require_sb()
    try:
        res = (
            sb.table("email_brief_subs")
            .update({"enabled": False})
            .eq("unsubscribe_token", token)
            .execute()
        )
    except Exception as e:
        logger.warning("unsubscribe failed: %s", e)
        raise HTTPException(status_code=500, detail="Could not unsubscribe.")
    return bool(res.data)


@router.post("/email-subscribe")
async def email_subscribe(authorization: str | None = Header(default=None)):
    """Opt the caller in, using the email on their Supabase account."""
    sb = _require_sb()
    user = verify_supabase_user(authorization)
    user_id = user["id"]
    email = user.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Account has no email address.")

    # Preserve an existing token so links in already-delivered mail keep working.
    try:
        existing = (
            sb.table("email_brief_subs")
            .select("unsubscribe_token")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rows = existing.data or []
    except Exception as e:
        logger.warning("subscribe lookup failed for %s: %s", user_id, e)
        rows = []

    token = (rows[0].get("unsubscribe_token") if rows else None) or secrets.token_urlsafe(24)

    try:
        sb.table("email_brief_subs").upsert(
            {
                "user_id": user_id,
                "email": email,
                "enabled": True,
                "unsubscribe_token": token,
            },
            on_conflict="user_id",
        ).execute()
    except Exception as e:
        logger.error("subscribe upsert failed for %s: %s", user_id, e)
        raise HTTPException(status_code=500, detail="Could not save subscription.")

    return {"subscribed": True, "email": email}


@router.get("/email-status")
async def email_status(authorization: str | None = Header(default=None)):
    sb = _require_sb()
    user_id = verify_supabase_user(authorization)["id"]
    try:
        res = (
            sb.table("email_brief_subs")
            .select("email,enabled,subscribed_at,last_brief_sent_at")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rows = res.data or []
    except Exception as e:
        logger.warning("status lookup failed for %s: %s", user_id, e)
        raise HTTPException(status_code=500, detail="Could not read subscription.")

    if not rows:
        return {"subscribed": False}
    row = rows[0]
    return {
        "subscribed": bool(row.get("enabled")),
        "email": row.get("email"),
        "subscribed_at": row.get("subscribed_at"),
        "last_brief_sent_at": row.get("last_brief_sent_at"),
    }


@router.delete("/email-subscribe")
async def email_unsubscribe_authed(authorization: str | None = Header(default=None)):
    sb = _require_sb()
    user_id = verify_supabase_user(authorization)["id"]
    try:
        sb.table("email_brief_subs").update({"enabled": False}).eq(
            "user_id", user_id
        ).execute()
    except Exception as e:
        logger.warning("unsubscribe failed for %s: %s", user_id, e)
        raise HTTPException(status_code=500, detail="Could not unsubscribe.")
    return {"subscribed": False}


@router.get("/email-unsubscribe")
async def email_unsubscribe_link(token: str = Query(...)):
    """Footer unsubscribe link, clicked from the mail body."""
    return _unsubscribe_page(token)


@router.post("/email-unsubscribe")
async def email_unsubscribe_one_click(token: str = Query(...)):
    """Gmail's native unsubscribe control, which POSTs rather than GETs."""
    return _unsubscribe_page(token)


def _unsubscribe_page(token: str) -> HTMLResponse:
    """Always reports success, so the endpoint can't be used to probe tokens."""
    _set_enabled_by_token(token)
    return HTMLResponse(
        "<!doctype html><html><body style=\"font:16px/1.5 -apple-system,Segoe UI,"
        "Roboto,Arial,sans-serif;padding:48px;text-align:center;color:#101828\">"
        "<h1 style=\"font-size:20px\">Unsubscribed</h1>"
        "<p style=\"color:#667085\">You will not get any more daily brief emails. "
        f"You can turn them back on any time from <a href=\"{WEB_APP_URL}\">"
        "FinContext settings</a>.</p></body></html>"
    )


@router.post("/send-daily-email")
async def send_daily_email(
    x_admin_token: str | None = Header(default=None),
    only_user_id: str | None = Query(
        default=None, description="Send to just this user. For testing."
    ),
):
    """Iterate every enabled subscriber, build their brief, and email it.

    Same contract as /api/telegram/send-daily-brief: idempotent, returns a
    summary, and never lets one bad subscriber abort the run.
    """
    _check_admin(x_admin_token)
    sb = _require_sb()
    if not email_sender.is_configured():
        raise HTTPException(status_code=503, detail="RESEND_API_KEY not set.")

    try:
        q = (
            sb.table("email_brief_subs")
            .select("user_id,email,unsubscribe_token")
            .eq("enabled", True)
        )
        if only_user_id:
            q = q.eq("user_id", only_user_id)
        targets = (q.execute().data) or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not list subscribers: {e}")

    # IST regardless of where the server runs; the brief is for an Indian
    # market audience.
    ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    today_label = ist_now.strftime("%a, %b %d")
    sent = 0
    skipped = 0
    failed = 0

    for t in targets:
        user_id = t.get("user_id")
        email = t.get("email")
        if not email:
            skipped += 1
            continue

        try:
            brief = build_user_brief(user_id)
        except Exception as e:
            logger.warning("email brief build failed for %s: %s", user_id, e)
            failed += 1
            continue
        if not brief:
            skipped += 1
            continue

        unsub = _unsubscribe_url(t.get("unsubscribe_token"))
        resp = email_sender.send_email(
            email,
            email_sender.brief_subject(today_label, brief),
            email_sender.format_daily_brief_html(
                user_name=None,
                today_label=today_label,
                web_url=WEB_APP_URL,
                brief=brief,
                unsubscribe_url=unsub,
            ),
            unsubscribe_url=unsub,
        )

        if resp.get("ok"):
            sent += 1
            update = {"last_brief_sent_at": datetime.now(timezone.utc).isoformat(),
                      "last_error": None}
        else:
            failed += 1
            update = {"last_error": str(resp.get("error"))[:500]}
        try:
            sb.table("email_brief_subs").update(update).eq("user_id", user_id).execute()
        except Exception:
            pass

    return {
        "targets": len(targets),
        "sent": sent,
        "skipped_no_holdings": skipped,
        "failed": failed,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
