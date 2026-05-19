"""
Policy & Regulatory News Ingestion
===================================
Fetches Indian government + regulatory press releases (PIB, RBI) on a 1-hour
cache. Each item is keyword-classified into one or more affected sectors so
the news-feed annotator can map "PLI scheme expansion to specialty steel" to
the user's JSW/Tata Steel/Jindal exposure even when the headline doesn't
name any specific company.

This is the *Indian wedge* — global LLM tools don't track PIB/RBI press
releases, so this gives FinContext a class of signal nobody else surfaces.

Output schema matches what `vector_store.ingest_news_items` and
`grounding.build_morning_brief_context` already expect, so policy items flow
through the existing news pipeline with a different `scope` tag:

    scope = "policy_pib"        government press release
    scope = "policy_rbi"        RBI press release / notification
    affected_sectors = [str]    derived via keyword match
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

import feedparser
import requests
from cachetools import TTLCache

logger = logging.getLogger(__name__)

# 1-hour cache. PIB / RBI publish in bursts; intra-hour refetches are wasteful.
_policy_cache: TTLCache = TTLCache(maxsize=8, ttl=60 * 60)

# When a feed fails (timeout, 5xx) we still want to bypass it for a while so a
# downed PIB/RBI server can't stall every Context Engine run. Short TTL — if
# the upstream recovers in 10 min we pick it back up automatically.
_policy_neg_cache: TTLCache = TTLCache(maxsize=32, ttl=10 * 60)

# Per-feed "we already logged the failure once" guard — same idea as in
# news_sources.py. RBI predictably returns 418 to Render IPs (Cloudflare anti-
# bot), and we don't need that line in the logs every Context Engine run.
_policy_logged_failure: set[str] = set()

# Hard cap on a single feed fetch. PIB/RBI are slow Indian gov servers; on a
# bad day they hang the TCP connect indefinitely. feedparser.parse() ignores
# timeouts entirely, so we MUST fetch bytes ourselves and hand them in.
_FEED_TIMEOUT_S = 6.0


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
# PIB has many RSS endpoints; RegId selects ministry/all. We pull the all-
# ministries feed AND the Finance ministry feed because Finance is high-density
# market signal that benefits from a separate path even with overlap.
PIB_FEEDS = [
    ("https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3",  "PIB India"),
    ("https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=10", "PIB Finance"),
]

# RBI publishes both Press Releases and Notifications via the same RSS gateway.
# Notifications are the binding ones (regulations); Press Releases include
# things like Monetary Policy statements + macro data releases.
RBI_FEEDS = [
    ("https://rbi.org.in/Scripts/rss.aspx?Type=Press_Release", "RBI Press Release"),
    ("https://rbi.org.in/Scripts/rss.aspx?Type=Notifications", "RBI Notification"),
]


# ---------------------------------------------------------------------------
# Sector classification — keyword-based.
# ---------------------------------------------------------------------------
# Deterministic, debuggable, fast. An item gets every sector tag whose keyword
# list has at least one match in headline+snippet. Curated to favour recall
# over precision — sectors are surfaced as chips, not used as filters, so a
# false positive is cheap and a false negative is expensive (user misses the
# personalization).
SECTOR_KEYWORDS: dict[str, list[str]] = {
    "Banking & Finance": [
        "repo rate", "monetary policy", "mpc", "interest rate", "npa",
        "capital adequacy", "nbfc", "scheduled commercial bank",
        "co-operative bank", "credit growth", "deposit growth",
        "kyc", "fraud", "wilful defaulter", "loan", "sarfaesi",
    ],
    "Auto": [
        "automobile", "auto sector", "ev policy", "electric vehicle",
        "fame ", "fame-ii", "scrappage", "automotive", "two-wheeler",
        "passenger vehicle", "commercial vehicle",
    ],
    "Energy & Power": [
        "renewable energy", "solar", "wind energy", "discom", "power sector",
        "thermal power", "coal india", "energy transition", "green hydrogen",
        "electricity", "transmission", "ups (ujwal", "ujwal discom", "udyog",
    ],
    "Defence": [
        "defence procurement", "defence ministry", "drdo", "indigenisation",
        "make in india defence", "armed forces", "naval", "air force",
        "negative import list",
    ],
    "Pharma & Healthcare": [
        "pharma", "pharmaceutical", "pli pharma", "drug pricing", "nppa",
        "medical device", "ayush", "vaccine", "ayushman",
    ],
    "Railways & Infrastructure": [
        "railway", "vande bharat", "bullet train", "infrastructure",
        "national highway", "nhai", "metro rail", "amrut", "smart city",
        "gati shakti", "pm gati shakti", "logistics",
    ],
    "Steel & Metals": [
        "steel", "iron ore", "specialty steel", "pli steel", "metals",
        "aluminium", "copper", "zinc", "lead", "mining",
    ],
    "Manufacturing & MSME": [
        "pli scheme", "manufacturing", "make in india", "skill india",
        "msme", "msmes", "ease of doing business",
    ],
    "Telecom": [
        "telecom", "5g ", "spectrum", "trai", "bsnl", "mobile services",
        "broadband", "right of way",
    ],
    "IT & Tech": [
        "it services", "data localisation", "data localization", "dpiit",
        "digital india", "data centre", "data center", "dpdp",
        "personal data protection",
    ],
    "Agriculture & Rural": [
        "msp ", "minimum support price", "farmer", "agriculture",
        "pmksy", "pm-kisan", "pm kisan", "rural development", "fertiliser",
        "fertilizer", "kharif", "rabi", "procurement",
    ],
    "Real Estate & Construction": [
        "rera", "housing", "real estate", "pmay", "pradhan mantri awas",
        "construction", "cement",
    ],
    "Oil & Gas": [
        "petroleum", "crude oil", "natural gas", "lpg ", "ongc",
        "city gas distribution", "refinery",
    ],
    "FMCG & Consumer": [
        "gst council", "consumer goods", "fmcg", "retail trade",
    ],
    "Textiles": [
        "textile", "garment", "cotton", "pli textile", "amended technology upgradation",
    ],
}


def _classify_sectors(text: str) -> list[str]:
    """Return every sector tag whose keyword list has a match in `text`.

    Lowercase substring matching — fast and good enough. Multiple sectors
    can match (e.g. an "EV battery + solar" item hits Auto + Energy).
    """
    if not text:
        return []
    lower = text.lower()
    matched: list[str] = []
    for sector, keywords in SECTOR_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                matched.append(sector)
                break
    return matched


def _strip_html(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"<[^>]+>", "", s).strip()


def _normalize_entry(entry: Any, source: str, scope: str) -> dict | None:
    """Convert a feedparser entry into the news pipeline schema.

    Returns None if the entry has no usable headline.
    """
    headline = (entry.get("title") or "").strip()
    if not headline:
        return None
    snippet = _strip_html(entry.get("summary") or "")[:280]

    published = ""
    if entry.get("published_parsed"):
        try:
            from time import strftime
            published = strftime("%Y-%m-%d", entry.published_parsed)
        except Exception:
            published = ""

    sectors = _classify_sectors(f"{headline} {snippet}")

    return {
        "source": source,
        "headline": headline,
        "snippet": snippet,
        "published_date": published,
        "url": entry.get("link"),
        "scope": scope,
        "affected_sectors": sectors,
    }


def _fetch_feed(url: str, source: str, scope: str, limit: int) -> list[dict]:
    """Fetch one feed defensively. Returns empty list on any failure — the
    outer pipeline falls back to whatever items succeeded.

    Uses requests with a hard timeout to fetch bytes, then hands them to
    feedparser. feedparser.parse(url) ignores socket timeouts and on PIB/RBI
    server hiccups would hang the calling SSE stream indefinitely.
    """
    if url in _policy_neg_cache:
        return []
    try:
        # PIB and RBI both block non-browser User-Agents (PIB returns 403, RBI
        # returns 418). Send a stock Chrome UA + the headers a real browser
        # would; without these the feeds 100% fail from a server IP.
        r = requests.get(
            url,
            timeout=_FEED_TIMEOUT_S,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "application/rss+xml, application/xml, text/xml, */*;q=0.8",
                "Accept-Language": "en-IN,en;q=0.9",
            },
        )
        r.raise_for_status()
        feed = feedparser.parse(r.content)
    except Exception as e:
        _policy_neg_cache[url] = True
        # Log once per process. RBI's 418 from Render is a known persistent
        # condition; PIB occasionally times out. The pipeline degrades
        # gracefully via the negative cache — no need to spam the log.
        if url not in _policy_logged_failure:
            _policy_logged_failure.add(url)
            logger.info("policy source unavailable (will retry after cache): %s — %s", source, type(e).__name__)
        return []
    out: list[dict] = []
    for entry in (feed.entries or [])[:limit]:
        item = _normalize_entry(entry, source=source, scope=scope)
        if item:
            out.append(item)
    return out


def _dedup_by_headline(items: list[dict]) -> list[dict]:
    """Cross-source dedup — PIB main + Finance feeds overlap heavily, and
    RBI Press Release + Notification occasionally do too."""
    seen: set[str] = set()
    out: list[dict] = []
    for it in items:
        key = (it.get("headline") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------
def fetch_pib_releases(limit_per_feed: int = 25) -> list[dict]:
    """Latest PIB government press releases. 1-hour cache."""
    cache_key = f"pib:{limit_per_feed}"
    if cache_key in _policy_cache:
        return _policy_cache[cache_key]
    items: list[dict] = []
    for url, source in PIB_FEEDS:
        items.extend(_fetch_feed(url, source, "policy_pib", limit_per_feed))
    items = _dedup_by_headline(items)
    _policy_cache[cache_key] = items
    return items


def fetch_rbi_notifications(limit_per_feed: int = 20) -> list[dict]:
    """Latest RBI press releases + notifications. 1-hour cache."""
    cache_key = f"rbi:{limit_per_feed}"
    if cache_key in _policy_cache:
        return _policy_cache[cache_key]
    items: list[dict] = []
    for url, source in RBI_FEEDS:
        items.extend(_fetch_feed(url, source, "policy_rbi", limit_per_feed))
    items = _dedup_by_headline(items)
    _policy_cache[cache_key] = items
    return items


def fetch_all_policy_items(limit_per_source: int = 20) -> list[dict]:
    """One-call: PIB + RBI combined, deduped, sector-tagged.

    Use this from `grounding.build_market_context` to add policy signal to
    the context every news-feed / movers / market-summary call already builds.
    """
    items: list[dict] = []
    items.extend(fetch_pib_releases(limit_per_feed=limit_per_source))
    items.extend(fetch_rbi_notifications(limit_per_feed=limit_per_source))
    return _dedup_by_headline(items)
