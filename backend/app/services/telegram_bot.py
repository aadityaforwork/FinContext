"""
Telegram Bot — API helpers + brief formatter
=============================================
Thin wrapper around Telegram's Bot API. Just two things:

  send_message(chat_id, text, ...)   — push a message to one chat
  format_daily_brief(payload)        — render the personalized morning brief

We intentionally don't use python-telegram-bot or aiogram. Send-only on the
backend + a webhook handler in `routers/telegram.py` is all we need; an extra
dependency is overkill for ~50 lines of HTTP.

Bot setup is documented in `scripts/README.md` under "Telegram bot v0".
"""

from __future__ import annotations

import html
import logging
import os
from typing import Iterable

import requests

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API = (
    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else None
)

# Telegram hard caps a message at 4096 chars. We aim for ~1500 — past that the
# brief stops being scannable on a phone.
MAX_MESSAGE_CHARS = 3500


def is_configured() -> bool:
    return TELEGRAM_BOT_TOKEN is not None


def send_message(
    chat_id: int | str,
    text: str,
    *,
    parse_mode: str = "HTML",
    disable_web_page_preview: bool = True,
    timeout: float = 10.0,
) -> dict:
    """Push one message to a chat. Returns the Telegram API response dict.

    Caller is responsible for chunking long messages — Telegram silently rejects
    anything past 4096 chars. We cap at MAX_MESSAGE_CHARS as a defensive trim.
    """
    if not TELEGRAM_API:
        logger.warning("send_message: TELEGRAM_BOT_TOKEN not set; skipping")
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN not configured"}

    payload = {
        "chat_id": chat_id,
        "text": text[:MAX_MESSAGE_CHARS],
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_web_page_preview,
    }
    try:
        r = requests.post(f"{TELEGRAM_API}/sendMessage", json=payload, timeout=timeout)
        return r.json()
    except Exception as e:
        logger.warning("Telegram sendMessage failed for %s: %s", chat_id, e)
        return {"ok": False, "error": str(e)}


def set_webhook(url: str, secret_token: str | None = None, timeout: float = 10.0) -> dict:
    """One-time call to register the webhook URL with Telegram.

    `secret_token` is sent back to us in the X-Telegram-Bot-Api-Secret-Token
    header on every webhook POST — we verify it in the router to reject forged
    payloads. Use the same value as the env var TELEGRAM_WEBHOOK_SECRET.
    """
    if not TELEGRAM_API:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN not configured"}
    payload: dict = {"url": url, "drop_pending_updates": True}
    if secret_token:
        payload["secret_token"] = secret_token
    try:
        r = requests.post(f"{TELEGRAM_API}/setWebhook", json=payload, timeout=timeout)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Brief formatting
# ---------------------------------------------------------------------------
# Telegram HTML supports a small tag set: <b>, <i>, <code>, <pre>, <a href>, <u>, <s>.
# We escape user-supplied text via html.escape and then wrap in those tags.
def _esc(s: str | None) -> str:
    if s is None:
        return ""
    return html.escape(str(s))


def _fmt_inr(n: float | None) -> str:
    if n is None:
        return "—"
    sign = "−" if n < 0 else ""
    return f"{sign}₹{abs(round(n)):,}"


def _fmt_signed_inr(n: float | None) -> str:
    if n is None:
        return "—"
    sign = "+" if n >= 0 else "−"
    return f"{sign}₹{abs(round(n)):,}"


def format_daily_brief(
    *,
    user_name: str | None,
    today_label: str | None,
    web_url: str | None,
    brief: dict,
) -> str:
    """Render the pre-market brief as Telegram HTML.

    `brief` is the dict returned by `routers.telegram._build_user_brief`:
        {
          portfolio:         {total_pnl, total_pnl_percent},
          movers:            [{ticker, move_percent, day_pnl_inr}, ...],
          holdings_today:    {ticker: {...}},
          indices:           {nifty_50: {value, change_percent}, ...},
          flows:             {fii_net_cr, dii_net_cr, ...} | None,
          policy_items:      [{headline, source, scope, affected_sectors,
                                affected_holdings}, ...],
          upcoming_earnings: [{ticker, date, days_ahead}, ...],
        }

    Sections are emitted only when their data is present, so the brief stays
    tight on quiet days and rich when there's a lot to say.
    """
    parts: list[str] = []

    # --- Header
    greeting = f"Hi {_esc(user_name)}, " if user_name else ""
    today = _esc(today_label) if today_label else ""
    parts.append(
        f"📊 <b>FinContext</b> — Pre-Market Brief"
        + (f"\n<i>{today} · NSE opens 9:15 AM IST</i>" if today else "")
    )
    if greeting:
        parts.append("")
        parts.append(greeting.rstrip(", ") + " — here's what to watch today.")

    # --- Yesterday's close: portfolio P&L + top contributors
    portfolio = brief.get("portfolio") or {}
    pnl = portfolio.get("total_pnl")
    pct = portfolio.get("total_pnl_percent")
    if pnl is not None:
        arrow = "📈" if pnl >= 0 else "📉"
        parts.append("")
        parts.append(
            f"{arrow} <b>Yesterday's close</b>: "
            f"{_fmt_signed_inr(pnl)}"
            + (f" ({pct:+.2f}%)" if pct is not None else "")
        )
        movers = list(brief.get("movers") or [])[:3]
        if movers:
            mover_strs = []
            for m in movers:
                t = _esc(m.get("ticker"))
                mp = m.get("move_percent") or 0
                d_pnl = m.get("day_pnl_inr")
                arrow = "▲" if mp >= 0 else "▼"
                pnl_str = f" ({_fmt_signed_inr(d_pnl)})" if d_pnl is not None else ""
                mover_strs.append(f"{arrow} <b>{t}</b> {mp:+.1f}%{pnl_str}")
            parts.append("Top: " + " · ".join(mover_strs))

    # --- Overnight: indices + FII/DII flows
    indices = brief.get("indices") or {}
    flows = brief.get("flows") or {}
    if indices or flows:
        parts.append("")
        parts.append("<b>🌐 Overnight</b>")
        idx_strs = []
        for label, key in [
            ("NIFTY 50", "nifty_50"),
            ("MIDCAP", "nifty_midcap_100"),
            ("SENSEX", "sensex"),
        ]:
            idx = indices.get(key)
            if not idx:
                continue
            v = idx.get("value")
            cp = idx.get("change_percent")
            if v is None:
                continue
            arrow = "▲" if (cp or 0) >= 0 else "▼"
            cp_str = f" {arrow}{abs(cp):.2f}%" if cp is not None else ""
            idx_strs.append(f"<b>{label}</b> {v:,.0f}{cp_str}")
        if idx_strs:
            parts.append(" · ".join(idx_strs))

        fii = flows.get("fii_net_cr") if isinstance(flows, dict) else None
        dii = flows.get("dii_net_cr") if isinstance(flows, dict) else None
        flow_strs = []
        if fii is not None:
            sign = "+" if fii >= 0 else "−"
            flow_strs.append(f"FII {sign}₹{abs(round(fii)):,} cr")
        if dii is not None:
            sign = "+" if dii >= 0 else "−"
            flow_strs.append(f"DII {sign}₹{abs(round(dii)):,} cr")
        if flow_strs:
            parts.append(" · ".join(flow_strs))

    # --- Policy & regulatory items hitting the user's sectors
    policy_items = brief.get("policy_items") or []
    if policy_items:
        parts.append("")
        parts.append("<b>📋 Policy &amp; regulatory · your sectors</b>")
        for i, p in enumerate(policy_items, 1):
            head = _esc((p.get("headline") or "")[:160])
            scope = p.get("scope") or ""
            tag = "RBI" if scope == "policy_rbi" else "PIB"
            sectors = p.get("affected_sectors") or []
            holdings = p.get("affected_holdings") or []
            parts.append(f"{i}. <b>{head}</b> [{tag}]")
            if sectors:
                parts.append(f"   <i>Sector: {_esc(' · '.join(sectors))}</i>")
            if holdings:
                parts.append(
                    f"   → Your: <b>{_esc(', '.join(holdings))}</b>"
                )

    # --- Upcoming earnings (next 7 days, your holdings)
    earnings = brief.get("upcoming_earnings") or []
    if earnings:
        parts.append("")
        parts.append("<b>📅 Earnings this week · your holdings</b>")
        for e in earnings:
            t = _esc(e.get("ticker"))
            date = _esc(e.get("date"))
            days = e.get("days_ahead")
            when = (
                "today" if days == 0
                else "tomorrow" if days == 1
                else f"in {days} days" if days is not None
                else date
            )
            parts.append(f"• <b>{t}</b> — {date} ({when})")

    # --- Footer
    parts.append("")
    if web_url:
        parts.append(f'<a href="{_esc(web_url)}">Open dashboard →</a>')
    parts.append(
        "<i>Educational only — not investment advice. "
        "Reply /off to pause daily briefs.</i>"
    )

    return "\n".join(parts)
