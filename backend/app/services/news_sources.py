"""
Multi-source Indian financial news pipeline.
============================================
Before: every news surface in the product (per-ticker, India headlines, global)
pulled from ONE source — Google News RSS. Google's ranking is stable over hours
so identical queries (and even similar queries — "INFY stock NSE" vs "TCS stock
NSE") returned the same 5 articles, making the dashboard and Context Engine
feel like they were stuck on yesterday's news.

This module adds genuine source variety:
  • Moneycontrol — markets / business / results
  • Economic Times — markets / company news
  • Livemint — markets / companies
  • Business Standard — markets
  • Hindu Business Line — markets
  • Google News (kept as a backstop)

Each fetch fans out to all sources concurrently with hard timeouts, merges the
results, deduplicates by normalized-title hash, and sorts by freshness. Per-feed
failures are isolated (one slow RBI server can't stall the whole pipeline).
"""

from __future__ import annotations

import hashlib
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import feedparser
import requests
from cachetools import TTLCache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feed registry
# ---------------------------------------------------------------------------
# Each entry: (feed_url, source_label, category).
# Category is informational for the UI; the pipeline doesn't filter on it yet,
# but it lets us bias the per-ticker filter ("results" category items more
# likely to mention a ticker by name, for example).
INDIAN_MARKET_FEEDS: list[tuple[str, str, str]] = [
    # Moneycontrol — dominant retail-investor source. `marketsnews.xml` 503s
    # under Render's IP load so we route around it via topnews/business/results
    # which serve from a different cache path.
    ("https://www.moneycontrol.com/rss/MCtopnews.xml",    "Moneycontrol",       "top"),
    ("https://www.moneycontrol.com/rss/business.xml",     "Moneycontrol",       "business"),
    ("https://www.moneycontrol.com/rss/results.xml",      "Moneycontrol",       "results"),
    # Economic Times — top-tier financial daily. Markets + headline streams.
    ("https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
                                                          "Economic Times",     "markets"),
    ("https://economictimes.indiatimes.com/rssfeedstopstories.cms",
                                                          "Economic Times",     "top"),
    # Economic Times — earnings stream. Earnings season carries the most
    # ticker-named headlines, which feed our per-ticker `fetch_for_ticker`.
    ("https://economictimes.indiatimes.com/markets/stocks/earnings/rssfeeds/1977021501.cms",
                                                          "Economic Times",     "earnings"),
    # Livemint — strong company-news desk.
    ("https://www.livemint.com/rss/markets",              "Livemint",           "markets"),
    ("https://www.livemint.com/rss/companies",            "Livemint",           "companies"),
    # Hindu Business Line — Chennai/south-India angle; useful for diversity.
    ("https://www.thehindubusinessline.com/markets/feeder/default.rss",
                                                          "Hindu BusinessLine", "markets"),
    # Business Standard's RSS endpoint 403s any non-residential IP (Render
    # included) so we don't ship it. Re-enable if we ever move to a proxy.
]

# Some feeds reject the bare "FinContext/1.0" UA we used before. Use a browser-
# realistic UA — same trick we use in policy_feeds.py for PIB.
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_FEED_TIMEOUT_S = 5.0

# Cache per-feed (key = url). 10-minute TTL — fresh enough that breaking news
# surfaces within ~10 min, slow enough to spare the upstreams.
_feed_cache: TTLCache = TTLCache(maxsize=64, ttl=10 * 60)

# Per-feed negative cache — if a feed times out or 5xxs, bypass it for 5 min.
_feed_neg_cache: TTLCache = TTLCache(maxsize=64, ttl=5 * 60)

# Per-feed "we already logged the failure once" guard. Some upstreams (BS 403,
# Moneycontrol 503 under load, RBI 418 from Render IPs) fail consistently. We
# want ONE log line per process so an oncall can see "this source is dead" once,
# not a wall of repeats every Context Engine run. Cleared on process restart.
_feed_logged_failure: set[str] = set()

# Shared executor for concurrent fetches. 8 workers is more than enough for our
# feed list and keeps Render's worker pool from getting starved.
_exec = ThreadPoolExecutor(max_workers=8, thread_name_prefix="news-rss")


# ---------------------------------------------------------------------------
# Single-feed fetch
# ---------------------------------------------------------------------------
def _parse_published(entry) -> str:
    """Best-effort ISO date string from an entry's published / updated field."""
    for field in ("published", "updated"):
        val = getattr(entry, field, None)
        if not val:
            continue
        try:
            dt = parsedate_to_datetime(val)
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            try:
                return val[:16]
            except Exception:
                pass
    return ""


def _parse_published_ts(entry) -> float:
    """Same as _parse_published but returns a unix ts for sorting. 0 if unknown."""
    for field in ("published", "updated"):
        val = getattr(entry, field, None)
        if not val:
            continue
        try:
            return parsedate_to_datetime(val).timestamp()
        except Exception:
            pass
    return 0.0


def _strip_html(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"<[^>]+>", "", s).strip()


def fetch_feed(url: str, source: str, category: str, limit: int = 12) -> list[dict]:
    """Fetch a single RSS feed. Returns up to `limit` items. Cached + neg-cached."""
    if url in _feed_cache:
        return _feed_cache[url][:limit]
    if url in _feed_neg_cache:
        return []
    try:
        r = requests.get(url, timeout=_FEED_TIMEOUT_S, headers={"User-Agent": _BROWSER_UA})
        r.raise_for_status()
        feed = feedparser.parse(r.content)
        out: list[dict] = []
        for entry in feed.entries[:limit]:
            headline = (entry.title or "").strip()
            if not headline:
                continue
            out.append({
                "source":         source,
                "category":       category,
                "headline":       headline,
                "snippet":        _strip_html(getattr(entry, "summary", "") or "")[:240] or headline,
                "url":            getattr(entry, "link", "") or "",
                "published_date": _parse_published(entry),
                "_ts":            _parse_published_ts(entry),
            })
        _feed_cache[url] = out
        return out
    except Exception as e:
        _feed_neg_cache[url] = True
        # Log a feed failure ONCE per process. Quiet by default — these feeds
        # fail predictably (BS blocks Render IPs with 403; Moneycontrol 503s
        # under load) and the multi-source pipeline handles it gracefully by
        # just using the survivors. No reason to flood logs with the same line.
        if url not in _feed_logged_failure:
            _feed_logged_failure.add(url)
            logger.info("RSS source unavailable (will use survivors): %s — %s", source, type(e).__name__)
        return []


# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------
_PUNCT_RE = re.compile(r"[^a-z0-9 ]+")
_WS_RE = re.compile(r"\s+")


def _normalize_title(t: str) -> str:
    """Aggressive normalization for dedup: lowercase, strip punctuation, keep
    first 10 tokens. Two outlets reporting the same Reuters-wire story will
    hit the same key even if their byline differs slightly."""
    t = t.lower()
    t = _PUNCT_RE.sub(" ", t)
    t = _WS_RE.sub(" ", t).strip()
    return " ".join(t.split()[:10])


def _title_key(t: str) -> str:
    return hashlib.md5(_normalize_title(t).encode("utf-8")).hexdigest()


def dedup_items(items: list[dict]) -> list[dict]:
    """Dedup a list of news items by normalized-title hash. Keeps the first
    occurrence, which after a freshness sort will be the most recent."""
    seen: set[str] = set()
    out: list[dict] = []
    for it in items:
        key = _title_key(it.get("headline", ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def fetch_india_market_pool(n: int = 18) -> list[dict]:
    """Fan-out fetch across all Indian market RSS feeds. Returns up to `n`
    deduplicated, freshness-sorted items.

    Resilience contract: this function NEVER raises. It returns whatever
    survived within the budget. Each individual feed already has its own 5s
    HTTP timeout; this outer ceiling is just a safety net against pathological
    cascades. If we hit it, we ship what we have — partial data is far better
    than a 500 to the morning-brief endpoint.
    """
    # Total budget is a generous 8 s — enough for 9 concurrent feeds on a cold
    # start (each individually capped at 5 s), but bounded so the Context
    # Engine SSE can't stall behind a runaway thread pool.
    budget_s = 8.0
    futures = [_exec.submit(fetch_feed, url, src, cat, 12) for url, src, cat in INDIAN_MARKET_FEEDS]

    items: list[dict] = []
    # Track which futures we've already harvested so the timeout-recovery path
    # doesn't double-count results.
    harvested: set[int] = set()
    try:
        for fut in as_completed(futures, timeout=budget_s):
            try:
                items.extend(fut.result() or [])
            except Exception as e:
                logger.info("feed future failed: %s", type(e).__name__)
            finally:
                harvested.add(id(fut))
    except TimeoutError:
        # Budget hit before all futures yielded. Cancel the stragglers so their
        # HTTP sockets don't tie up workers and ship whatever already arrived.
        for f in futures:
            if id(f) not in harvested and not f.done():
                # cancel() is best-effort on threads, but it at least prevents
                # us from harvesting them on a subsequent call.
                f.cancel()
        done_count = sum(1 for f in futures if f.done())
        logger.info("news pool partial fetch: %d/%d feeds done, shipping partial",
                    done_count, len(futures))

    # Freshness sort BEFORE dedup so we keep the most recent variant of each story.
    items.sort(key=lambda x: x.get("_ts", 0), reverse=True)
    items = dedup_items(items)
    # Drop the private _ts field before returning to consumers — internal only.
    for it in items:
        it.pop("_ts", None)
    return items[:n]


def google_news_for_query(query: str, hl: str = "en-IN", gl: str = "IN",
                          ceid: str = "IN:en", n: int = 8) -> list[dict]:
    """Google News RSS for a specific query (kept as backstop / per-ticker)."""
    cache_key = f"gnews|{query}|{hl}|{gl}|{ceid}"
    if cache_key in _feed_cache:
        return _feed_cache[cache_key][:n]
    try:
        url = (f"https://news.google.com/rss/search?q={quote(query)}"
               f"&hl={hl}&gl={gl}&ceid={ceid}")
        r = requests.get(url, timeout=_FEED_TIMEOUT_S, headers={"User-Agent": _BROWSER_UA})
        r.raise_for_status()
        feed = feedparser.parse(r.content)
        out = []
        for entry in feed.entries[:n + 4]:
            headline = (entry.title or "").strip()
            if not headline:
                continue
            # Google's title format: "Headline - Source"
            parts = headline.rsplit(" - ", 1)
            clean_headline = parts[0].strip()
            source = parts[1].strip() if len(parts) > 1 else "Google News"
            out.append({
                "source":         source,
                "category":       "google",
                "headline":       clean_headline,
                "snippet":        _strip_html(getattr(entry, "summary", "") or "")[:240] or clean_headline,
                "url":            getattr(entry, "link", "") or "",
                "published_date": _parse_published(entry),
            })
        _feed_cache[cache_key] = out
        return out[:n]
    except Exception as e:
        logger.warning("Google News fetch failed for '%s': %s", query, e)
        return []


def fetch_for_ticker(ticker: str, company_name: str, sector: str | None,
                     n: int = 6) -> list[dict]:
    """Per-ticker news. Strategy:
        1. Google News for the company name (specific, ticker-focused).
        2. Filter the general Indian-market pool for items mentioning the
           company name OR ticker — surfaces stories from the trusted Indian
           desks (Moneycontrol/ET/Mint/BS) that Google's ranking missed.
        3. Merge + dedup + freshness sort.

    Returns up to `n` items.
    """
    company_q = company_name or ticker
    # 1. Google — specific query
    google_items = google_news_for_query(
        f"{company_q} stock NSE", hl="en-IN", gl="IN", ceid="IN:en", n=n + 2
    )

    # 2. General pool — filter by ticker / company-name mention
    pool = fetch_india_market_pool(n=24)
    company_l = (company_q or "").lower()
    ticker_l = ticker.lower()
    # Use the first significant word of the company name to catch "TCS",
    # "Infosys", "Reliance Industries" → "infosys". 3+ chars to avoid noise.
    primary_token = next(
        (w for w in company_l.split() if len(w) >= 4),
        company_l,
    )
    pool_matches = [
        n for n in pool
        if primary_token in (n["headline"] + " " + n.get("snippet", "")).lower()
        or ticker_l in (n["headline"] + " " + n.get("snippet", "")).lower()
    ]

    merged = google_items + pool_matches
    merged = dedup_items(merged)
    # Sort by freshness (items without dates fall to bottom).
    merged.sort(
        key=lambda x: x.get("published_date") or "",
        reverse=True,
    )
    return merged[:n]


def warm_pool() -> None:
    """Optional prewarm: fire all feeds in background so the first user request
    isn't cold. Safe to call repeatedly."""
    try:
        fetch_india_market_pool(n=24)
    except Exception as e:
        logger.warning("news_sources warm_pool failed: %s", e)
