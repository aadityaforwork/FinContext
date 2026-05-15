"""
Telegram Router
===============
Three concerns, separated by auth model:

  1. PUBLIC (Telegram → us)
       POST /api/telegram/webhook      — incoming user messages / commands
       Auth: X-Telegram-Bot-Api-Secret-Token header (set when registering webhook)

  2. AUTHED USER (frontend → us)
       POST   /api/telegram/link-code  — generate a 6-char code to enter in chat
       GET    /api/telegram/link-status — am I linked? which @username?
       DELETE /api/telegram/link       — unlink
       Auth: Bearer <supabase_access_token>; verified via supabase.auth.get_user()

  3. ADMIN (cron → us)
       POST /api/telegram/send-daily-brief
       Auth: X-Admin-Token header

The bot has FOUR commands:
  /start            welcome + how-to
  /link CODE        bind this chat to a FinContext account using a 6-char code
  /off              pause daily briefs
  /on               resume daily briefs

The daily brief is intentionally LLM-free for v0 — it's a deterministic
portfolio P&L + top movers + latest policy headlines. Reliable + fast +
no hallucination risk. The richer LLM-annotated view stays in the web app.
"""

from __future__ import annotations

import logging
import os
import secrets
import string
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from supabase import create_client

from app.services import grounding, policy_feeds, telegram_bot
from app.services.grounding import _fetch_fast_snapshot, _upcoming_earnings
from app.nse_universe import TICKER_TO_META, resolve_yf_symbol

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/telegram", tags=["telegram"])

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")
WEB_APP_URL = os.getenv("WEB_APP_URL", "https://fincontext.app")

_sb = None
if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    try:
        _sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        logger.info("Telegram router: supabase service client initialized")
    except Exception as e:
        logger.error("Telegram router: supabase init failed: %s", e)

# Code parameters — short enough to type comfortably, large enough to dodge brute force
LINK_CODE_LEN = 6
LINK_CODE_TTL_MIN = 10
_CODE_ALPHABET = string.ascii_uppercase + string.digits


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def _verify_supabase_jwt(authorization: str | None) -> str:
    """Resolve the caller's Supabase user_id from the Authorization header.

    Goes direct to the Supabase Auth REST endpoint via `requests` instead of
    `_sb.auth.get_user(jwt)` — the Python SDK mixes its own service-role
    session state with the user JWT you pass, which produces spurious
    "Session from session_id claim in JWT does not exist" 401s after a token
    rotation. Hitting `/auth/v1/user` directly is what the JS SDK does and
    avoids the mixed-state bug.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured.")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    token = authorization.split(" ", 1)[1].strip()
    try:
        r = requests.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                # Auth server requires a project key in the apikey header even
                # when the bearer carries the user JWT. Service-role works.
                "apikey": SUPABASE_SERVICE_KEY,
            },
            timeout=5,
        )
    except requests.RequestException as e:
        logger.warning("supabase auth/user request failed: %s", e)
        raise HTTPException(status_code=503, detail="Auth check failed.")
    if r.status_code != 200:
        logger.info(
            "supabase auth/user rejected JWT: %s %s",
            r.status_code,
            (r.text or "")[:200],
        )
        raise HTTPException(status_code=401, detail="Invalid token.")
    user = r.json() or {}
    user_id = user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")
    return user_id


def _check_admin(token: str | None) -> None:
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="ADMIN_TOKEN not configured.")
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid admin token.")


def _check_webhook_secret(secret: str | None) -> None:
    """Telegram echoes the secret_token we set with setWebhook in this header
    on every incoming POST. If unset on our side we can't validate; we still
    accept (useful for local dev) but log a warning."""
    if not TELEGRAM_WEBHOOK_SECRET:
        logger.warning("TELEGRAM_WEBHOOK_SECRET unset — webhook is unauthenticated")
        return
    if secret != TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid webhook secret.")


# ---------------------------------------------------------------------------
# Endpoint: link-code (frontend → us)
# ---------------------------------------------------------------------------
class LinkCodeOut(BaseModel):
    code: str
    expires_at: str


@router.post("/link-code", response_model=LinkCodeOut)
async def create_link_code(authorization: str | None = Header(default=None)):
    """Generate a fresh 6-char code the user pastes into the Telegram chat.

    Single-use, 10-min TTL. Old unused codes for the same user are replaced.
    """
    user_id = _verify_supabase_jwt(authorization)
    code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(LINK_CODE_LEN))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=LINK_CODE_TTL_MIN)
    try:
        # Drop the user's previous code (if any) so a single user never has
        # two valid codes floating around at the same time.
        _sb.table("telegram_link_codes").delete().eq("user_id", user_id).execute()
        _sb.table("telegram_link_codes").insert({
            "code": code,
            "user_id": user_id,
            "expires_at": expires_at.isoformat(),
        }).execute()
    except Exception as e:
        logger.exception("link-code insert failed")
        raise HTTPException(status_code=500, detail=f"Could not create code: {e}")
    return LinkCodeOut(code=code, expires_at=expires_at.isoformat())


# ---------------------------------------------------------------------------
# Endpoint: link-status (frontend → us)
# ---------------------------------------------------------------------------
@router.get("/link-status")
async def link_status(authorization: str | None = Header(default=None)):
    user_id = _verify_supabase_jwt(authorization)
    try:
        res = (
            _sb.table("telegram_links")
            .select("telegram_username,linked_at,daily_brief_enabled")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rows = res.data or []
    except Exception as e:
        logger.warning("link-status fetch failed: %s", e)
        return {"linked": False}
    if not rows:
        return {"linked": False}
    row = rows[0]
    return {
        "linked": True,
        "telegram_username": row.get("telegram_username"),
        "linked_at": row.get("linked_at"),
        "daily_brief_enabled": row.get("daily_brief_enabled", True),
    }


# ---------------------------------------------------------------------------
# Endpoint: unlink (frontend → us)
# ---------------------------------------------------------------------------
@router.delete("/link")
async def unlink(authorization: str | None = Header(default=None)):
    user_id = _verify_supabase_jwt(authorization)
    try:
        _sb.table("telegram_links").delete().eq("user_id", user_id).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unlink failed: {e}")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Endpoint: webhook (Telegram → us)
# ---------------------------------------------------------------------------
@router.post("/webhook")
async def webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    """Receive incoming user messages from Telegram. Idempotent — Telegram
    retries on non-2xx, so we always return 200 unless auth fails."""
    _check_webhook_secret(x_telegram_bot_api_secret_token)

    try:
        update = await request.json()
    except Exception:
        return {"ok": True}  # malformed payload — ignore

    msg = update.get("message") or update.get("edited_message") or {}
    text = (msg.get("text") or "").strip()
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    from_user = msg.get("from") or {}
    tg_username = from_user.get("username")

    if not chat_id or not text:
        return {"ok": True}

    cmd, _, arg = text.partition(" ")
    cmd = cmd.lower()

    if cmd == "/start":
        telegram_bot.send_message(
            chat_id,
            "👋 Welcome to <b>FinContext</b>.\n\n"
            "I'll send you a personalized morning brief every weekday at "
            "8:30 AM IST — your P&amp;L, top movers, news hitting your portfolio, "
            "and policy items affecting your sectors.\n\n"
            "<b>To get started:</b>\n"
            f"1. Open <a href=\"{WEB_APP_URL}\">FinContext</a> → Settings → Connect Telegram\n"
            "2. Copy the 6-character code shown\n"
            "3. Send it back here as <code>/link CODE</code>\n\n"
            "Other commands: /off pause briefs · /on resume · /help",
        )
    elif cmd == "/help":
        telegram_bot.send_message(
            chat_id,
            "<b>FinContext bot</b>\n"
            "/link CODE — bind this chat to your FinContext account\n"
            "/off — pause daily briefs\n"
            "/on — resume daily briefs\n"
            "/start — welcome message",
        )
    elif cmd == "/link":
        code = (arg or "").strip().upper()
        if not code:
            telegram_bot.send_message(chat_id, "Usage: <code>/link CODE</code>")
        else:
            _handle_link_command(chat_id, code, tg_username)
    elif cmd == "/off":
        _set_brief_enabled(chat_id, False)
        telegram_bot.send_message(chat_id, "🔕 Daily briefs paused. Send /on to resume.")
    elif cmd == "/on":
        _set_brief_enabled(chat_id, True)
        telegram_bot.send_message(chat_id, "🔔 Daily briefs enabled.")
    # Any other text — ignore silently to keep the bot non-chatty.

    return {"ok": True}


def _handle_link_command(chat_id: int, code: str, tg_username: str | None) -> None:
    """Validate a /link CODE attempt. Replies in-chat on success or failure."""
    if not _sb:
        telegram_bot.send_message(chat_id, "⚠️ Backend isn't configured for linking.")
        return
    try:
        res = (
            _sb.table("telegram_link_codes")
            .select("user_id,expires_at")
            .eq("code", code)
            .limit(1)
            .execute()
        )
        rows = res.data or []
    except Exception as e:
        logger.warning("link lookup failed: %s", e)
        telegram_bot.send_message(chat_id, "⚠️ Couldn't verify the code right now. Try again.")
        return

    if not rows:
        telegram_bot.send_message(chat_id, "❌ That code isn't valid. Generate a new one in the web app.")
        return

    row = rows[0]
    expires_at = row.get("expires_at")
    if expires_at:
        try:
            exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if exp_dt < datetime.now(timezone.utc):
                telegram_bot.send_message(chat_id, "⏰ That code expired. Generate a new one in the web app.")
                _sb.table("telegram_link_codes").delete().eq("code", code).execute()
                return
        except Exception:
            pass

    user_id = row["user_id"]
    try:
        _sb.table("telegram_links").upsert({
            "user_id": user_id,
            "telegram_chat_id": chat_id,
            "telegram_username": tg_username,
            "linked_at": datetime.now(timezone.utc).isoformat(),
            "daily_brief_enabled": True,
        }, on_conflict="user_id").execute()
        # Burn the code so it can't be reused
        _sb.table("telegram_link_codes").delete().eq("code", code).execute()
    except Exception as e:
        logger.exception("link upsert failed")
        telegram_bot.send_message(chat_id, f"⚠️ Couldn't link: {e}")
        return

    telegram_bot.send_message(
        chat_id,
        "✅ Linked! Your morning brief will arrive at 8:30 AM IST every weekday.\n\n"
        "Use /off any time to pause.",
    )


def _set_brief_enabled(chat_id: int, enabled: bool) -> None:
    if not _sb:
        return
    try:
        _sb.table("telegram_links") \
            .update({"daily_brief_enabled": enabled}) \
            .eq("telegram_chat_id", chat_id).execute()
    except Exception as e:
        logger.warning("set_brief_enabled failed: %s", e)


# ---------------------------------------------------------------------------
# Endpoint: send-daily-brief (cron → us)
# ---------------------------------------------------------------------------
_brief_pool = ThreadPoolExecutor(max_workers=8)


def _build_user_brief(user_id: str) -> dict | None:
    """Build the pre-market brief payload for one user.

    Sent ~8:30 AM IST — NSE opens at 9:15, so framing is *yesterday's close +
    overnight*, NOT "today's movers" (those don't exist yet at this hour).

    Pulled from already-cached sources, no LLM call:
      - per-holding live snapshot (fast_info, 5-min cache) for yesterday's
        close P&L + top contributors
      - market context (10-min cache) for indices, FII/DII flows, policy
        headlines from PIB + RBI overnight
      - upcoming earnings per holding (12-h cache)

    Filters policy items to those affecting the user's actual sectors so the
    brief stays relevant — a steel PLI release goes only to people holding
    steel names.
    """
    try:
        positions_res = (
            _sb.table("portfolio")
            .select("ticker,quantity,buy_price")
            .eq("user_id", user_id)
            .execute()
        )
        positions = positions_res.data or []
    except Exception as e:
        logger.warning("brief: positions fetch failed for %s: %s", user_id, e)
        positions = []

    if not positions:
        return None  # no holdings → no brief

    # ---- Per-holding live snapshot (yesterday's close P&L) ----
    holdings_today: dict[str, dict] = {}
    movers_list: list[dict] = []
    total_pnl = 0.0
    total_value = 0.0
    for p in positions:
        ticker = (p.get("ticker") or "").upper()
        qty = float(p.get("quantity") or 0)
        if not ticker or qty <= 0:
            continue
        try:
            snap = _fetch_fast_snapshot(ticker)
        except Exception:
            snap = None
        if not snap or not snap.get("current_price"):
            continue
        price = float(snap["current_price"])
        change_pct = float(snap.get("change_percent") or 0)
        prev = price / (1 + change_pct / 100.0) if change_pct > -99.99 else price
        day_pnl = qty * (price - prev)
        cur_val = qty * price
        holdings_today[ticker] = {
            "current_price": round(price, 2),
            "change_percent": round(change_pct, 2),
            "quantity": qty,
            "current_value_inr": round(cur_val, 2),
            "day_pnl_inr": round(day_pnl, 2),
        }
        total_pnl += day_pnl
        total_value += cur_val
        movers_list.append({
            "ticker": ticker,
            "move_percent": round(change_pct, 2),
            "day_pnl_inr": round(day_pnl, 2),
        })

    if total_value > 0:
        for t in holdings_today:
            holdings_today[t]["weight_pct"] = round(
                holdings_today[t]["current_value_inr"] / total_value * 100, 2
            )

    pct = (total_pnl / total_value * 100) if total_value > 0 else 0
    portfolio = {"total_pnl": round(total_pnl, 2), "total_pnl_percent": round(pct, 2)}

    # Top 3 movers by absolute ₹ contribution (more meaningful than %)
    movers_list.sort(key=lambda m: abs(m.get("day_pnl_inr") or 0), reverse=True)
    top_movers = movers_list[:3]

    # ---- Market context: indices, FII/DII flows, policy items ----
    try:
        market_ctx = grounding.build_market_context() or {}
    except Exception as e:
        logger.warning("brief: market_context failed: %s", e)
        market_ctx = {}

    indices = market_ctx.get("indices") or {}
    flows = market_ctx.get("flows")
    all_policy = market_ctx.get("policy_headlines") or []

    # ---- Filter policy items to user's sectors ----
    # Map each user holding to its sector via TICKER_TO_META, then keep only
    # policy items whose `affected_sectors` overlaps the user's sector set.
    holdings_by_sector: dict[str, list[str]] = {}
    user_sectors: set[str] = set()
    for ticker in holdings_today:
        sector = (TICKER_TO_META.get(ticker) or {}).get("sector") or "Unknown"
        holdings_by_sector.setdefault(sector, []).append(ticker)
        user_sectors.add(sector)

    relevant_policy: list[dict] = []
    for p in all_policy:
        affected = set(p.get("affected_sectors") or [])
        # Match either by exact sector name OR by partial keyword (the policy
        # tags like "Banking & Finance" don't always match TICKER_TO_META's
        # "Banks", "Financial Services" — coarse match is intentional).
        intersection: list[str] = []
        for sec in affected:
            sec_lower = sec.lower()
            for user_sec in user_sectors:
                if sec_lower in user_sec.lower() or user_sec.lower() in sec_lower:
                    intersection.append(user_sec)
        intersection = sorted(set(intersection))
        if not intersection:
            continue
        # Collect the user's specific tickers in those matched sectors.
        affected_holdings: list[str] = []
        for s in intersection:
            affected_holdings.extend(holdings_by_sector.get(s, []))
        relevant_policy.append({
            "headline": p.get("headline"),
            "source": p.get("source"),
            "scope": p.get("scope"),
            "affected_sectors": intersection,
            "affected_holdings": sorted(set(affected_holdings)),
        })
    relevant_policy = relevant_policy[:5]

    # ---- Upcoming earnings (next 7 days) for the user's holdings ----
    upcoming_earnings: list[dict] = []
    for ticker in list(holdings_today.keys())[:15]:  # cap to bound yfinance load
        try:
            e = _upcoming_earnings(ticker, max_days=7)
        except Exception:
            e = None
        if e:
            upcoming_earnings.append({"ticker": ticker, **e})
    upcoming_earnings.sort(key=lambda x: x.get("days_ahead", 99))
    upcoming_earnings = upcoming_earnings[:5]

    return {
        "portfolio": portfolio,
        "movers": top_movers,
        "holdings_today": holdings_today,
        "indices": indices,
        "flows": flows,
        "policy_items": relevant_policy,
        "upcoming_earnings": upcoming_earnings,
    }


@router.post("/send-daily-brief")
async def send_daily_brief(x_admin_token: str | None = Header(default=None)):
    """Iterate every linked user with daily_brief_enabled=true, build their
    deterministic brief, and push to Telegram. Returns a summary."""
    _check_admin(x_admin_token)
    if not _sb:
        raise HTTPException(status_code=503, detail="Supabase not configured.")
    if not telegram_bot.is_configured():
        raise HTTPException(status_code=503, detail="TELEGRAM_BOT_TOKEN not set.")

    try:
        res = (
            _sb.table("telegram_links")
            .select("user_id,telegram_chat_id,telegram_username")
            .eq("daily_brief_enabled", True)
            .execute()
        )
        targets = res.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not list links: {e}")

    # Format date in IST (UTC+5:30) regardless of where the server runs —
    # the brief is for an Indian-market audience.
    ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    today_label = ist_now.strftime("%a, %b %d")
    sent = 0
    skipped = 0
    failed = 0

    for t in targets:
        try:
            brief = _build_user_brief(t["user_id"])
        except Exception as e:
            logger.warning("brief build failed for %s: %s", t["user_id"], e)
            failed += 1
            continue
        if not brief:
            skipped += 1
            continue
        text = telegram_bot.format_daily_brief(
            user_name=t.get("telegram_username"),
            today_label=today_label,
            web_url=WEB_APP_URL,
            brief=brief,
        )
        resp = telegram_bot.send_message(t["telegram_chat_id"], text)
        if resp.get("ok"):
            sent += 1
            try:
                _sb.table("telegram_links") \
                    .update({"last_brief_sent_at": datetime.now(timezone.utc).isoformat()}) \
                    .eq("user_id", t["user_id"]).execute()
            except Exception:
                pass
        else:
            failed += 1
            # If the user blocked the bot, Telegram returns 403 — disable so we
            # don't keep spamming attempts.
            err_desc = (resp.get("description") or "").lower()
            if "forbidden" in err_desc or "blocked" in err_desc:
                try:
                    _sb.table("telegram_links") \
                        .update({"daily_brief_enabled": False}) \
                        .eq("user_id", t["user_id"]).execute()
                except Exception:
                    pass

    return {
        "targets": len(targets),
        "sent": sent,
        "skipped_no_holdings": skipped,
        "failed": failed,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
