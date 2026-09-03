"""
Data Ingestion Service
======================
This module handles the data collection and retrieval pipeline.
It is STRICTLY DECOUPLED from the LLM generation layer (llm_engine.py).

Architecture:
    Raw Data Sources → data_ingestion.py → Context Docs → llm_engine.py → User

Current: Fetches real, freshness-filtered news via news_sources' multi-source
pipeline. There is deliberately NO synthetic fallback — see retrieve_context.
Production: Will add embedding generation + vector store integration.
"""

import logging

from cachetools import TTLCache

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


def retrieve_context(ticker: str, query: str | None = None, top_k: int = 5) -> list[dict]:
    """
    Retrieve relevant context documents for a given ticker.

    Strategy (multi-source, post-fix):
    1. Pull from news_sources.fetch_for_ticker — this fans out across
       Moneycontrol / ET / Livemint / Business Standard / Hindu BusinessLine
       AND Google News, dedupes by normalized title, sorts by freshness.
    2. If the user passed an explicit `query`, supplement with a targeted
       Google search on that query.
    3. Return whatever survived — possibly nothing.

    The previous version pulled from Google News only — which meant the same
    5 articles ranked for any IT-stock query (TCS/INFY/WIPRO/HCLTECH) showed
    up identically, making the news feed feel stuck.

    NO SYNTHETIC FALLBACK, deliberately. This used to end with "if fewer than
    2 items, return NEWS_CORPUS[ticker]" — hand-written MVP demo headlines,
    served to the LLM as if they were real reporting. It was near-unreachable
    while every source was unfiltered (something always came back), and it
    happened to be inert for most portfolios because its keys are the old demo
    names ("TATAMOTORS-TMCV", not "TMCV"). Adding the freshness filter to the
    per-ticker path made "fewer than 2 items" the common case, which would
    have turned a dormant landmine into the default answer for every quiet
    stock. An empty list is the honest result: the attribution surface already
    has an `unexplained` bucket and `data_gaps` for exactly this, and a real
    "no recent catalyst" beats an invented one (AGENTS.md rule 1).

    Callers must handle []. Nothing here has ever guaranteed a non-empty list
    — every source could already fail at once — so this widens an existing
    case rather than introducing a new one.

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
    from app.services.marketdata import news_sources

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

    # Cache only a non-empty result. An empty list is far more often "the feed
    # hiccuped" than "this company has no news", and the upstream Google call
    # is already cached inside news_sources for 10 min, so re-asking costs
    # nothing on the common path while letting a transient failure recover.
    if news:
        _news_cache[cache_key] = news
        logger.info(f"Retrieved {len(news)} multi-source news items for {ticker}")
    else:
        logger.info(f"No news inside the freshness window for {ticker}")
    return news[:top_k]


def ingest_news_batch(articles: list[dict]) -> int:
    """
    Ingest a batch of news articles into the vector store.
    TODO: Implement when vector store is connected.
    """
    raise NotImplementedError("Vector store ingestion not yet implemented")
