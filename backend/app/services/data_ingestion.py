"""
Data Ingestion Service
======================
This module handles the data collection and retrieval pipeline.
It is STRICTLY DECOUPLED from the LLM generation layer (llm_engine.py).

Architecture:
    Raw Data Sources → data_ingestion.py → Context Docs → llm_engine.py → User

Current: Fetches real news from Google News RSS + falls back to seed data.
Production: Will add embedding generation + vector store integration.
"""

import feedparser
import logging
from urllib.parse import quote
from cachetools import TTLCache
from app.seed_data import NEWS_CORPUS
from app.nse_universe import TICKER_TO_META

logger = logging.getLogger(__name__)

# News cache: 15 min TTL, max 20 entries
_news_cache = TTLCache(maxsize=20, ttl=900)

# ---------------------------------------------------------------------------
# TODO: Embedding Model Integration (same as before)
# ---------------------------------------------------------------------------
# In production, this module will:
# 1. Initialize embedding model: SentenceTransformer('all-MiniLM-L6-v2')
# 2. Connect to vector store: Pinecone / pgvector
# 3. MLOps monitoring: MLflow tracking for retrieval metrics
# ---------------------------------------------------------------------------


def _fetch_google_news(query: str, num_results: int = 8) -> list[dict]:
    """
    Fetch news articles from Google News RSS feed.
    
    Args:
        query: Search query string
        num_results: Max number of results to return
    
    Returns:
        List of dicts with: source, headline, snippet, published_date
    """
    try:
        encoded_query = quote(query)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"

        # feedparser.parse(url) has no timeout — on a slow Google News response
        # this would hang the calling thread indefinitely and stall the whole
        # Context Engine SSE. Fetch bytes with a hard timeout instead.
        import requests as _rq
        r = _rq.get(url, timeout=5.0, headers={"User-Agent": "FinContext/1.0"})
        r.raise_for_status()
        feed = feedparser.parse(r.content)
        
        results = []
        for entry in feed.entries[:num_results]:
            # Google News title format: "Headline - Source Name"
            title_parts = entry.title.rsplit(" - ", 1)
            headline = title_parts[0].strip()
            source = title_parts[1].strip() if len(title_parts) > 1 else "Google News"
            
            # Extract date
            published = ""
            if hasattr(entry, "published"):
                try:
                    from datetime import datetime
                    from email.utils import parsedate_to_datetime
                    dt = parsedate_to_datetime(entry.published)
                    published = dt.strftime("%Y-%m-%d")
                except Exception:
                    published = entry.published[:10] if len(entry.published) >= 10 else ""
            
            # Extract snippet from description (strip HTML)
            snippet = ""
            if hasattr(entry, "summary"):
                import re
                snippet = re.sub(r"<[^>]+>", "", entry.summary).strip()[:300]
            
            results.append({
                "source": source,
                "headline": headline,
                "snippet": snippet if snippet else headline,
                "relevance_score": round(0.95 - (len(results) * 0.05), 2),  # Decreasing relevance
                "published_date": published,
            })
        
        return results
    except Exception as e:
        logger.warning(f"Google News fetch failed for query '{query}': {e}")
        return []


def retrieve_context(ticker: str, query: str | None = None, top_k: int = 5) -> list[dict]:
    """
    Retrieve relevant context documents for a given ticker.

    Strategy (multi-source, post-fix):
    1. Pull from news_sources.fetch_for_ticker — this fans out across
       Moneycontrol / ET / Livemint / Business Standard / Hindu BusinessLine
       AND Google News, dedupes by normalized title, sorts by freshness.
    2. If the user passed an explicit `query`, supplement with a targeted
       Google search on that query.
    3. Fall back to seed data only if every source returns empty.

    The previous version pulled from Google News only — which meant the same
    5 articles ranked for any IT-stock query (TCS/INFY/WIPRO/HCLTECH) showed
    up identically, making the news feed feel stuck.

    Args:
        ticker: Stock ticker symbol
        query: Optional natural-language query — adds a focused Google call
        top_k: Number of documents to retrieve

    Returns:
        List of context documents sorted by freshness, with `relevance_score`
        attached for back-compat with seed-data ranking consumers.
    """
    cache_key = f"context_{ticker}_{query or ''}"
    if cache_key in _news_cache:
        return _news_cache[cache_key][:top_k]

    meta = TICKER_TO_META.get(ticker, {})
    stock_name = meta.get("name", ticker)
    sector = meta.get("sector", "")

    # Lazy import to avoid circular dependency at module load.
    from app.services import news_sources

    # 1. Multi-source ticker pull
    news: list[dict] = news_sources.fetch_for_ticker(
        ticker, stock_name, sector, n=top_k + 3
    )

    # 2. Optional supplement when caller provides a custom query
    if query:
        try:
            extra = news_sources.google_news_for_query(
                f"{stock_name} {query}", hl="en-IN", gl="IN", ceid="IN:en",
                n=top_k,
            )
            news = news_sources.dedup_items(news + extra)
        except Exception as e:
            logger.warning(f"Custom query fetch failed for {ticker}: {e}")

    # Attach relevance_score for back-compat: rank is freshness-derived, with
    # the first item highest. Old callers (seed_data sort) keep working.
    for i, item in enumerate(news):
        item.setdefault("relevance_score", round(0.95 - i * 0.05, 2))

    if len(news) >= 2:
        _news_cache[cache_key] = news
        logger.info(f"Retrieved {len(news)} multi-source news items for {ticker}")
        return news[:top_k]

    # 3. Fall back to seed data only if everything else came up empty
    logger.info(f"Falling back to seed data for {ticker}")
    corpus = NEWS_CORPUS.get(ticker, [])
    fallback = sorted(corpus, key=lambda x: x["relevance_score"], reverse=True)[:top_k]
    return fallback


def ingest_news_batch(articles: list[dict]) -> int:
    """
    Ingest a batch of news articles into the vector store.
    TODO: Implement when vector store is connected.
    """
    raise NotImplementedError("Vector store ingestion not yet implemented")
