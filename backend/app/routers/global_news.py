"""
Global News Router
==================
Endpoints for fetching country-specific financial news
and analyzing portfolio impact using Gemini AI.
"""

import re
import feedparser
import logging
from urllib.parse import quote
from cachetools import TTLCache
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.services import ai_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/global-news", tags=["global-news"])

# -----------------------------------------------------------------------
# Country Configuration
# -----------------------------------------------------------------------
COUNTRY_CONFIG = {
    "IN": {
        "name": "India",
        "flag": "🇮🇳",
        "query": "India economy stock market finance when:1d",
        "hl": "en-IN", "gl": "IN", "ceid": "IN:en",
    },
    "US": {
        "name": "United States",
        "flag": "🇺🇸",
        "query": "US economy stock market Federal Reserve Wall Street when:1d",
        "hl": "en-US", "gl": "US", "ceid": "US:en",
    },
    "CN": {
        "name": "China",
        "flag": "🇨🇳",
        "query": "China economy trade market finance when:1d",
        "hl": "en", "gl": "US", "ceid": "US:en",
    },
    "EU": {
        "name": "Europe",
        "flag": "🇪🇺",
        "query": "Europe economy ECB stock market finance when:1d",
        "hl": "en", "gl": "US", "ceid": "US:en",
    },
    "JP": {
        "name": "Japan",
        "flag": "🇯🇵",
        "query": "Japan economy Nikkei Bank of Japan finance when:1d",
        "hl": "en", "gl": "US", "ceid": "US:en",
    },
    "GB": {
        "name": "United Kingdom",
        "flag": "🇬🇧",
        "query": "UK economy FTSE Bank of England finance when:1d",
        "hl": "en-GB", "gl": "GB", "ceid": "GB:en",
    },
    "SA": {
        "name": "Middle East",
        "flag": "🇸🇦",
        "query": "Middle East oil OPEC economy Saudi Arabia finance when:1d",
        "hl": "en", "gl": "US", "ceid": "US:en",
    },
    "RU": {
        "name": "Russia",
        "flag": "🇷🇺",
        "query": "Russia economy sanctions oil energy market when:1d",
        "hl": "en", "gl": "US", "ceid": "US:en",
    },
}

# News cache: 15-min TTL, max 20 entries
_news_cache = TTLCache(maxsize=20, ttl=300)


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------
def _fetch_news(country_code: str, num_results: int = 8) -> list[dict]:
    """Fetch financial news for a country from Google News RSS."""
    cfg = COUNTRY_CONFIG.get(country_code)
    if not cfg:
        return []

    cache_key = f"globe_{country_code}"
    if cache_key in _news_cache:
        return _news_cache[cache_key]

    try:
        encoded = quote(cfg["query"])
        url = (
            f"https://news.google.com/rss/search?q={encoded}"
            f"&hl={cfg['hl']}&gl={cfg['gl']}&ceid={cfg['ceid']}"
        )
        feed = feedparser.parse(url)

        results = []
        for entry in feed.entries[:num_results]:
            title_parts = entry.title.rsplit(" - ", 1)
            headline = title_parts[0].strip()
            source = title_parts[1].strip() if len(title_parts) > 1 else "Google News"

            published = ""
            if hasattr(entry, "published"):
                try:
                    from datetime import datetime
                    from email.utils import parsedate_to_datetime
                    dt = parsedate_to_datetime(entry.published)
                    published = dt.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    published = entry.published[:16] if len(entry.published) >= 16 else ""

            snippet = ""
            if hasattr(entry, "summary"):
                snippet = re.sub(r"<[^>]+>", "", entry.summary).strip()[:300]

            results.append({
                "headline": headline,
                "source": source,
                "snippet": snippet or headline,
                "published_date": published,
                "url": getattr(entry, "link", ""),
            })

        _news_cache[cache_key] = results
        return results

    except Exception as e:
        logger.warning(f"Google News fetch failed for {country_code}: {e}")
        return []


# -----------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------
@router.get("/countries")
async def list_countries():
    """Return the list of supported countries with metadata."""
    return [
        {"code": code, "name": cfg["name"], "flag": cfg["flag"]}
        for code, cfg in COUNTRY_CONFIG.items()
    ]


@router.get("/{country_code}")
async def get_country_news(country_code: str):
    """Fetch financial news for a specific country/region."""
    country_code = country_code.upper()
    if country_code not in COUNTRY_CONFIG:
        raise HTTPException(status_code=404, detail=f"Unsupported country code: {country_code}")

    cfg = COUNTRY_CONFIG[country_code]
    news = _fetch_news(country_code)

    return {
        "country_code": country_code,
        "country_name": cfg["name"],
        "flag": cfg["flag"],
        "news": news,
    }


class PortfolioImpactRequest(BaseModel):
    country_code: str
    headlines: list[str]
    tickers: Optional[list[str]] = None  # user's watchlist/portfolio tickers


@router.post("/portfolio-impact")
async def analyze_portfolio_impact(req: PortfolioImpactRequest):
    """Use Gemini AI to analyze how a country's news might impact the user's portfolio."""
    country_code = req.country_code.upper()
    cfg = COUNTRY_CONFIG.get(country_code)
    if not cfg:
        raise HTTPException(status_code=404, detail="Unsupported country code")

    has_portfolio = bool(req.tickers)
    portfolio_str = ", ".join(req.tickers) if has_portfolio else "No specific stocks"
    headlines_str = "\n".join([f"- {h}" for h in req.headlines[:6]])

    if not ai_client.is_available():
        return {
            "impact_summary": f"AI analysis unavailable. News from {cfg['name']} may affect the Indian stock market depending on sector exposure.",
            "affected_stocks": [],
        }

    # Build a cite-able CONTEXT block: each headline gets an id like "headlines[0]".
    indexed_headlines = [
        {"id": f"headlines[{i}]", "text": h} for i, h in enumerate(req.headlines[:6])
    ]
    context = {
        "country": cfg["name"],
        "country_code": country_code,
        "headlines": indexed_headlines,
        "user_portfolio_tickers": req.tickers or [],
    }

    if has_portfolio:
        task = (
            f"Assess how the news in CONTEXT.headlines may impact each of the user's Indian "
            f"holdings (CONTEXT.user_portfolio_tickers). For every affected stock, the `reason` "
            f"MUST cite the headline id (e.g. \"headlines[2]\"). If no headline actually implies "
            f"impact on a holding, exclude it."
        )
    else:
        task = (
            "Assess how the news in CONTEXT.headlines may impact Indian market sectors/indices. "
            "For every affected sector/index, the `reason` MUST cite the headline id that "
            "supports it."
        )
    schema = """{
  "impact_summary": str,
  "affected_stocks": [
    { "ticker": str,
      "impact": "positive" | "negative" | "neutral",
      "reason": { "text": str, "source": str } }
  ],
  "confidence": "low" | "medium" | "high",
  "data_gaps": [ str, ... ]
}"""

    try:
        data = ai_client.generate_grounded_json(task, context, schema, max_tokens=1024)
        if not data:
            raise ValueError("empty response")
        return data
    except Exception as e:
        logger.error(f"Grounded portfolio-impact call failed: {e}")
        return {
            "impact_summary": f"These events from {cfg['name']} may impact Indian markets through trade, currency, and sentiment channels. Monitor NIFTY and relevant sectoral indices.",
            "affected_stocks": [],
            "confidence": "low",
            "data_gaps": ["AI call failed — fallback message shown."],
        }
