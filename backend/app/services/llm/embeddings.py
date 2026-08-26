"""
Embeddings service
==================
Thin wrapper around OpenAI's text-embedding-3-small (1536 dims, cheap, fast).

Used to:
  1. Embed each NSE stock's business description once (catalog backfill).
  2. Embed each incoming news headline as it lands in our pipeline.

Both vectors flow into Supabase `stock_embeddings` and `news_embeddings`
tables (see supabase/migrations/002_pgvector_semantic_news.sql).
"""

import hashlib
import logging
import os
from typing import Iterable

from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
EMBED_DIM = 1536  # text-embedding-3-small native dimension

_client = None
if os.getenv("OPENAI_API_KEY"):
    try:
        from openai import OpenAI
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        logger.info(f"Embeddings client enabled (model={EMBED_MODEL}).")
    except Exception as e:
        logger.error(f"Failed to initialize embeddings client: {e}")
        _client = None
else:
    logger.warning("OPENAI_API_KEY not set — embedding features will be disabled.")


def is_available() -> bool:
    return _client is not None


def content_hash(text: str) -> str:
    """Stable short hash for dedup (sha256 → first 32 hex chars)."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:32]


def embed(text: str) -> list[float] | None:
    """Single-text embedding. Returns None if client missing or text empty."""
    if not _client or not text:
        return None
    try:
        # Hard cap input — model context is 8191 tokens but we never need that much.
        resp = _client.embeddings.create(
            model=EMBED_MODEL,
            input=text[:4000],
        )
        return resp.data[0].embedding
    except Exception as e:
        logger.warning(f"embed() failed: {e}")
        return None


def embed_batch(texts: Iterable[str], chunk: int = 100) -> list[list[float] | None]:
    """Batch embedding — OpenAI accepts up to 2048 inputs per call. We chunk to
    100 to stay well under request-size limits and to recover gracefully if a
    single batch errors out.

    Returns a list aligned 1:1 with input. Failed items get None.
    """
    items = list(texts)
    if not _client or not items:
        return [None] * len(items)

    out: list[list[float] | None] = []
    for i in range(0, len(items), chunk):
        batch = [t[:4000] if t else "" for t in items[i : i + chunk]]
        # OpenAI rejects empty strings — replace with a single space placeholder
        # then null out the result for that position.
        empty_positions = [j for j, t in enumerate(batch) if not t.strip()]
        for j in empty_positions:
            batch[j] = " "
        try:
            resp = _client.embeddings.create(model=EMBED_MODEL, input=batch)
            vecs = [d.embedding for d in resp.data]
            for j in empty_positions:
                vecs[j] = None
            out.extend(vecs)
        except Exception as e:
            logger.warning(f"embed_batch chunk {i} failed: {e}")
            out.extend([None] * len(batch))
    return out
