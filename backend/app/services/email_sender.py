"""
Email sender
============
Sends the daily brief over email via Resend's HTTPS API.

Resend rather than SMTP on purpose: Render's outbound SMTP is unreliable and
slow to diagnose, while this is a plain HTTPS POST that fails loudly.

Mirrors telegram_bot.py: is_configured() + a send that never raises + a
format_daily_brief_* renderer fed by the same _build_user_brief payload.
"""

from __future__ import annotations

import html
import logging
import os

import requests

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_API = "https://api.resend.com/emails"

# Until a domain is verified in Resend, onboarding@resend.dev is the only
# sender that works, and it can only deliver to the account owner's address.
BRIEF_EMAIL_FROM = os.getenv("BRIEF_EMAIL_FROM", "FinContext <onboarding@resend.dev>")


def is_configured() -> bool:
    return RESEND_API_KEY is not None


def send_email(
    to: str,
    subject: str,
    html_body: str,
    *,
    unsubscribe_url: str | None = None,
    timeout: float = 20.0,
) -> dict:
    """Send one email. Returns {"ok": bool, "id"|"error": ...} and never raises.

    `unsubscribe_url` becomes a List-Unsubscribe header so Gmail renders its
    native unsubscribe control, which keeps a recurring send out of spam.
    """
    if not RESEND_API_KEY:
        logger.warning("send_email: RESEND_API_KEY not set; skipping")
        return {"ok": False, "error": "RESEND_API_KEY not configured"}

    payload: dict = {
        "from": BRIEF_EMAIL_FROM,
        "to": [to],
        "subject": subject,
        "html": html_body,
    }
    if unsubscribe_url:
        payload["headers"] = {
            "List-Unsubscribe": f"<{unsubscribe_url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        }

    try:
        r = requests.post(
            RESEND_API,
            json=payload,
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            timeout=timeout,
        )
    except Exception as e:
        logger.warning("Resend send failed for %s: %s", to, e)
        return {"ok": False, "error": str(e)}

    if r.status_code >= 300:
        detail = (r.text or "")[:300]
        logger.warning("Resend rejected send to %s: %s %s", to, r.status_code, detail)
        return {"ok": False, "error": f"HTTP {r.status_code}: {detail}"}

    try:
        body = r.json()
    except Exception:
        body = {}
    return {"ok": True, "id": body.get("id")}


def _esc(s: str | None) -> str:
    if s is None:
        return ""
    return html.escape(str(s))


def _fmt_signed_inr(n: float | None) -> str:
    if n is None:
        return "-"
    sign = "+" if n >= 0 else "-"
    return f"{sign}&#8377;{abs(round(n)):,}"


# Inline styles only, and tables for layout. Gmail strips <style> blocks and
# Outlook ignores flex/grid.
_INK = "#101828"
_MUTED = "#667085"
_BORDER = "#e4e7ec"
_UP = "#0f7b3d"
_DOWN = "#b42318"
_BG = "#f5f6f8"
_FONT = "-apple-system,Segoe UI,Roboto,Arial,sans-serif"

_H2 = (
    f"margin:0 0 10px;font:600 12px/1.4 {_FONT};letter-spacing:.06em;"
    f"text-transform:uppercase;color:{_MUTED}"
)
_BODY = f"margin:0;font:400 15px/1.55 {_FONT};color:{_INK}"
_SMALL = f"margin:0;font:400 13px/1.5 {_FONT};color:{_MUTED}"
_DOT = " &nbsp;&middot;&nbsp; "


def _section(inner: str) -> str:
    return f'<tr><td style="padding:20px 28px;border-top:1px solid {_BORDER}">{inner}</td></tr>'


def brief_subject(today_label: str | None, brief: dict) -> str:
    """Lead with the P&L number so the brief is useful from the inbox list."""
    portfolio = brief.get("portfolio") or {}
    pnl = portfolio.get("total_pnl")
    date_part = f" · {today_label}" if today_label else ""
    if pnl is None:
        return f"FinContext Pre-Market Brief{date_part}"
    sign = "+" if pnl >= 0 else "-"
    return f"Pre-Market Brief{date_part} · {sign}₹{abs(round(pnl)):,}"


def _pnl_section(brief: dict) -> str | None:
    portfolio = brief.get("portfolio") or {}
    pnl = portfolio.get("total_pnl")
    if pnl is None:
        return None
    pct = portfolio.get("total_pnl_percent")
    color = _UP if pnl >= 0 else _DOWN
    pct_str = f" ({pct:+.2f}%)" if pct is not None else ""
    inner = (
        f'<p style="{_H2}">Yesterday&#39;s close</p>'
        f'<p style="margin:0;font:600 30px/1.2 {_FONT};color:{color}">'
        f'{_fmt_signed_inr(pnl)}'
        f'<span style="font-size:16px;font-weight:400">{pct_str}</span></p>'
    )

    movers = list(brief.get("movers") or [])[:3]
    if movers:
        cells = []
        for m in movers:
            mp = m.get("move_percent") or 0
            mcolor = _UP if mp >= 0 else _DOWN
            d_pnl = m.get("day_pnl_inr")
            pnl_str = (
                f'<br><span style="font-size:12px;color:{_MUTED}">'
                f'{_fmt_signed_inr(d_pnl)}</span>'
                if d_pnl is not None
                else ""
            )
            cells.append(
                f'<td style="padding:10px 14px 0 0;{_BODY}">'
                f'<b>{_esc(m.get("ticker"))}</b> '
                f'<span style="color:{mcolor}">{mp:+.1f}%</span>{pnl_str}</td>'
            )
        inner += (
            '<table role="presentation" cellpadding="0" cellspacing="0" '
            f'style="margin-top:10px"><tr>{"".join(cells)}</tr></table>'
        )
    return inner


def _overnight_section(brief: dict) -> str | None:
    indices = brief.get("indices") or {}
    flows = brief.get("flows") or {}
    if not indices and not flows:
        return None

    lines: list[str] = []
    idx_parts = []
    for label, key in [
        ("NIFTY 50", "nifty_50"),
        ("MIDCAP", "nifty_midcap_100"),
        ("SENSEX", "sensex"),
    ]:
        idx = indices.get(key)
        if not idx or idx.get("value") is None:
            continue
        cp = idx.get("change_percent")
        if cp is None:
            cp_str = ""
        else:
            arrow = "&#9650;" if cp >= 0 else "&#9660;"
            cp_str = (
                f' <span style="color:{_UP if cp >= 0 else _DOWN}">'
                f'{arrow}{abs(cp):.2f}%</span>'
            )
        idx_parts.append(f'<b>{label}</b> {idx["value"]:,.0f}{cp_str}')
    if idx_parts:
        lines.append(_DOT.join(idx_parts))

    flow_parts = []
    for label, key in [("FII", "fii_net_cr"), ("DII", "dii_net_cr")]:
        v = flows.get(key) if isinstance(flows, dict) else None
        if v is None:
            continue
        sign = "+" if v >= 0 else "-"
        flow_parts.append(f"{label} {sign}&#8377;{abs(round(v)):,} cr")
    if flow_parts:
        lines.append(_DOT.join(flow_parts))

    if not lines:
        return None
    body = "".join(f'<p style="{_BODY};margin-top:6px">{ln}</p>' for ln in lines)
    return f'<p style="{_H2}">Overnight</p>{body}'


def _policy_section(brief: dict) -> str | None:
    policy_items = brief.get("policy_items") or []
    if not policy_items:
        return None

    items = []
    for p in policy_items:
        tag = "RBI" if (p.get("scope") or "") == "policy_rbi" else "PIB"
        head = _esc((p.get("headline") or "")[:200])
        meta = []
        sectors = p.get("affected_sectors") or []
        holdings = p.get("affected_holdings") or []
        if sectors:
            meta.append(_esc(" · ".join(sectors)))
        if holdings:
            meta.append(f'Your: <b>{_esc(", ".join(holdings))}</b>')
        meta_str = (
            f'<p style="{_SMALL};margin-top:3px">{" &nbsp;|&nbsp; ".join(meta)}</p>'
            if meta
            else ""
        )
        items.append(
            f'<p style="{_BODY};margin-top:14px">'
            f'<span style="padding:1px 6px;margin-right:6px;border:1px solid {_BORDER};'
            f'border-radius:3px;font-size:11px;color:{_MUTED}">{tag}</span>'
            f'{head}</p>{meta_str}'
        )
    return (
        f'<p style="{_H2}">Policy &amp; regulatory &middot; your sectors</p>'
        + "".join(items)
    )


def _earnings_section(brief: dict) -> str | None:
    earnings = brief.get("upcoming_earnings") or []
    if not earnings:
        return None

    items = []
    for e in earnings:
        days = e.get("days_ahead")
        when = (
            "today" if days == 0
            else "tomorrow" if days == 1
            else f"in {days} days" if days is not None
            else _esc(e.get("date"))
        )
        items.append(
            f'<p style="{_BODY};margin-top:8px"><b>{_esc(e.get("ticker"))}</b> '
            f'<span style="color:{_MUTED}">{_esc(e.get("date"))} ({when})</span></p>'
        )
    return (
        f'<p style="{_H2}">Earnings this week &middot; your holdings</p>'
        + "".join(items)
    )


def format_daily_brief_html(
    *,
    user_name: str | None,
    today_label: str | None,
    web_url: str | None,
    brief: dict,
    unsubscribe_url: str | None = None,
) -> str:
    """Render the pre-market brief as an email-client-safe HTML document.

    Takes the same `brief` dict as telegram_bot.format_daily_brief, so both
    channels stay in sync by construction. Sections are emitted only when their
    data is present.
    """
    rows = [
        _section(inner)
        for inner in (
            _pnl_section(brief),
            _overnight_section(brief),
            _policy_section(brief),
            _earnings_section(brief),
        )
        if inner
    ]
    if not rows:
        rows.append(
            _section(
                f'<p style="{_BODY}">No holdings tracked yet. Add positions in the '
                f'dashboard to start getting a personalized brief.</p>'
            )
        )

    greeting = (
        f'<p style="{_SMALL};margin-top:6px">Hi {_esc(user_name)}, here&#39;s what to '
        f'watch today.</p>'
        if user_name
        else ""
    )
    header = (
        f'<tr><td style="padding:28px 28px 20px">'
        f'<p style="margin:0;font:700 20px/1.2 {_FONT};color:{_INK}">'
        f'FinContext Pre-Market Brief</p>'
        f'<p style="{_SMALL};margin-top:6px">'
        + (f"{_esc(today_label)}{_DOT}" if today_label else "")
        + "NSE opens 9:15 AM IST</p>"
        + greeting
        + "</td></tr>"
    )

    cta = (
        f'<p style="margin:0 0 14px"><a href="{_esc(web_url)}" '
        f'style="padding:10px 18px;background:{_INK};color:#fff;text-decoration:none;'
        f'border-radius:6px;font:600 14px/1 {_FONT}">Open dashboard</a></p>'
        if web_url
        else ""
    )
    unsub = (
        f'{_DOT}<a href="{_esc(unsubscribe_url)}" style="color:{_MUTED}">Unsubscribe</a>'
        if unsubscribe_url
        else ""
    )
    footer = (
        f'<tr><td style="padding:20px 28px 28px;border-top:1px solid {_BORDER}">'
        f'{cta}<p style="{_SMALL}">Educational only, not investment advice.{unsub}</p>'
        f'</td></tr>'
    )

    return (
        f'<!doctype html><html><body style="margin:0;padding:24px 12px;background:{_BG}">'
        f'<table role="presentation" cellpadding="0" cellspacing="0" width="100%" '
        f'style="max-width:600px;margin:0 auto;background:#fff;'
        f'border:1px solid {_BORDER};border-radius:10px">'
        f'{header}{"".join(rows)}{footer}'
        f'</table></body></html>'
    )
