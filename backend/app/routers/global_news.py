"""
Global News Router
==================
Endpoints for fetching country-specific financial news
and analyzing portfolio impact using Gemini AI.
"""

import os
import re
import feedparser
import logging
from urllib.parse import quote
from cachetools import TTLCache
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import google.generativeai as genai
from dotenv import load_dotenv

from app.db import get_db
from app.db.models import PortfolioPosition

logger = logging.getLogger(__name__)

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

_model = None
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    _model = genai.GenerativeModel("gemini-2.0-flash")

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


@router.post("/portfolio-impact")
async def analyze_portfolio_impact(
    req: PortfolioImpactRequest,
    db: AsyncSession = Depends(get_db),
):
    """Use Gemini AI to analyze how a country's news might impact the user's portfolio."""
    country_code = req.country_code.upper()
    cfg = COUNTRY_CONFIG.get(country_code)
    if not cfg:
        raise HTTPException(status_code=404, detail="Unsupported country code")

    # Fetch portfolio holdings
    result = await db.execute(select(PortfolioPosition))
    positions = result.scalars().all()

    has_portfolio = len(positions) > 0
    portfolio_str = ", ".join([f"{p.ticker} (qty: {p.quantity})" for p in positions]) if has_portfolio else "No specific stocks"
    headlines_str = "\n".join([f"- {h}" for h in req.headlines[:6]])

    if not _model:
        return {
            "impact_summary": f"AI analysis unavailable. News from {cfg['name']} may affect the Indian stock market depending on sector exposure.",
            "affected_stocks": [],
        }

    if has_portfolio:
        prompt = f"""You are a senior global macro analyst.

The user holds these Indian stocks: {portfolio_str}

Latest news from {cfg['name']}:
{headlines_str}

Analyze concisely:
1. Impact summary (2-3 sentences) on the Indian stock market and user's portfolio.
2. For each affected stock: ticker, impact (positive/negative/neutral), one-line reason.

Respond ONLY in JSON (no markdown fences):
{{"impact_summary": "...", "affected_stocks": [{{"ticker": "...", "impact": "positive|negative|neutral", "reason": "..."}}]}}
"""
    else:
        prompt = f"""You are a senior global macro analyst.

Latest news from {cfg['name']}:
{headlines_str}

Analyze how these events might impact the Indian stock market and key sectors.
Provide:
1. Impact summary (2-3 sentences)
2. List 3-5 Indian market sectors/indices that could be affected.

Respond ONLY in JSON (no markdown fences):
{{"impact_summary": "...", "affected_stocks": [{{"ticker": "NIFTY50", "impact": "positive|negative|neutral", "reason": "..."}}]}}
"""

    try:
        response = _model.generate_content(prompt)
        text = response.text.strip()
        # Strip any markdown formatting
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

        import json
        data = json.loads(text)
        return data

    except Exception as e:
        logger.error(f"Gemini portfolio impact analysis failed: {e}")
        return {
            "impact_summary": f"These events from {cfg['name']} may impact Indian markets through trade, currency, and sentiment channels. Monitor NIFTY and relevant sectoral indices.",
            "affected_stocks": [],
        }
