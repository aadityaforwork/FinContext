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
    portfolio: dict | None,
    news_items: Iterable[dict],
    movers: Iterable[dict],
    holdings_today: dict | None,
    web_url: str | None = None,
    today_label: str | None = None,
    max_news: int = 4,
    max_movers: int = 3,
) -> str:
    """Render the personalized morning brief as Telegram-flavored HTML.

    Inputs use the same shape as the news_feed + movers backend payloads, so
    the cron script can pass them straight through with no reshaping.
    """
    parts: list[str] = []

    # --- Header
    greeting = f"Hi {_esc(user_name)}, " if user_name else ""
    today = _esc(today_label) if today_label else ""
    parts.append(
        f"📊 <b>FinContext</b>"
        + (f" — {today}" if today else "")
    )
    if greeting:
        parts.append(greeting + "your portfolio brief is ready.")

    # --- Portfolio top strip
    if portfolio:
        pnl = portfolio.get("total_pnl")
        pct = portfolio.get("total_pnl_percent")
        if pnl is not None and pct is not None:
            arrow = "📈" if pnl >= 0 else "📉"
            parts.append("")
            parts.append(
                f"{arrow} <b>Portfolio today</b>: "
                f"{_fmt_signed_inr(pnl)} ({pct:+.2f}%)"
            )

    # --- Top movers
    movers_list = list(movers)[:max_movers]
    if movers_list:
        parts.append("")
        parts.append("<b>📊 Today's movers</b>")
        for m in movers_list:
            ticker = _esc(m.get("ticker"))
            mp = m.get("move_percent")
            arrow = "▲" if (mp or 0) >= 0 else "▼"
            holding = (holdings_today or {}).get((m.get("ticker") or "").upper())
            stake_str = ""
            if holding and holding.get("day_pnl_inr") is not None:
                stake_str = f" · your {_fmt_signed_inr(holding['day_pnl_inr'])}"
            attribution = (m.get("attribution") or [{}])[0].get("text") if m.get("attribution") else ""
            attr_str = ""
            if attribution:
                attr_str = f"\n   <i>{_esc(attribution[:140])}</i>"
            parts.append(
                f"• <b>{ticker}</b> {arrow} {mp:+.1f}%{stake_str}{attr_str}"
            )

    # --- Top news
    news_list = list(news_items)[:max_news]
    if news_list:
        parts.append("")
        parts.append("<b>📰 News hitting your portfolio</b>")
        for i, n in enumerate(news_list, 1):
            head = _esc((n.get("headline") or "")[:140])
            impact = (n.get("impact_level") or "").upper()
            tags = []
            if impact:
                tags.append(impact)
            if (n.get("scope") or "").startswith("policy_"):
                tags.append("RBI" if n["scope"] == "policy_rbi" else "POLICY")
            tag_str = f" [{' · '.join(tags)}]" if tags else ""
            parts.append(f"{i}. <b>{head}</b>{tag_str}")
            reason = n.get("reason")
            if reason:
                parts.append(f"   <i>{_esc(reason[:200])}</i>")
            # Compute aggregate stake across affected tickers
            affected = n.get("affected_tickers") or []
            if affected and holdings_today:
                day_pnl = 0.0
                hits = 0
                for t in affected:
                    h = holdings_today.get((t or "").upper())
                    if h and h.get("day_pnl_inr") is not None:
                        day_pnl += h["day_pnl_inr"]
                        hits += 1
                if hits > 0:
                    label = affected[0] if hits == 1 else f"{hits} positions"
                    parts.append(
                        f"   → your {_esc(label)}: today {_fmt_signed_inr(day_pnl)}"
                    )

    # --- Footer
    parts.append("")
    if web_url:
        parts.append(f'<a href="{_esc(web_url)}">Open dashboard →</a>')
    parts.append(
        "<i>Educational only — not investment advice. "
        "Reply /off to pause daily briefs.</i>"
    )

    return "\n".join(parts)
