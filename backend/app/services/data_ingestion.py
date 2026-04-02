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
        
        feed = feedparser.parse(url)
        
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
    
    Strategy:
    1. Try to fetch real news from Google News RSS
    2. Fall back to seed data if fetching fails
    
    In production, this will use vector similarity search.
    
    Args:
        ticker: Stock ticker symbol
        query: Optional natural-language query
        top_k: Number of documents to retrieve
    
    Returns:
        List of context documents sorted by relevance score
    """
    cache_key = f"context_{ticker}"
    if cache_key in _news_cache:
        return _news_cache[cache_key][:top_k]
    
    # Build an effective search query
    meta = TICKER_TO_META.get(ticker, {})
    stock_name = meta.get("name", ticker)
    sector = meta.get("sector", "")
    
    search_query = f"{stock_name} stock {sector} NSE"
    if query:
        search_query = f"{stock_name} {query}"
    
    # Try real news first
    news = _fetch_google_news(search_query, num_results=top_k + 3)
    
    if len(news) >= 2:
        # Got real news — use it
        _news_cache[cache_key] = news
        logger.info(f"Retrieved {len(news)} real news articles for {ticker}")
        return news[:top_k]
    
    # Fall back to seed data
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
