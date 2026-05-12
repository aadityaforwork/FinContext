-- =============================================================================
-- FinContext — pgvector semantic retrieval for news → portfolio matching
-- =============================================================================
-- Prereq: enable the pgvector extension first
--   Supabase Dashboard → Database → Extensions → search "vector" → Enable
-- (Or run `CREATE EXTENSION IF NOT EXISTS vector;` from the SQL editor.)
--
-- After enabling, paste this whole file into Supabase SQL editor → Run.
--
-- What this creates:
--   1. stock_embeddings — one row per NSE ticker, with its business description
--      embedded as a 1536-dim vector. Backfilled once from the backend.
--   2. news_embeddings — rolling window of recent news headlines + their vectors.
--      Populated as news is fetched in the data pipeline.
--   3. match_news_for_tickers — RPC the backend calls. Given a user's ticker
--      universe, returns the top-N semantically similar news from the recency
--      window. THIS IS THE KILLER FEATURE: surfaces news affecting a stock
--      even when the stock isn't named in the headline.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- =============================================================================
-- 1. Stock embeddings — knowledge layer for the user's universe
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.stock_embeddings (
  ticker       text PRIMARY KEY,
  name         text,
  sector       text,
  description  text,
  embedding    vector(1536),
  updated_at   timestamptz DEFAULT now()
);

-- HNSW index for fast cosine similarity. Built once over the catalog.
CREATE INDEX IF NOT EXISTS stock_embeddings_hnsw_idx
  ON public.stock_embeddings
  USING hnsw (embedding vector_cosine_ops);

-- RLS: this is reference data, readable by anyone authenticated.
-- Writes happen only via service-role key from the backend.
ALTER TABLE public.stock_embeddings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "stock_embeddings_read_all" ON public.stock_embeddings;
CREATE POLICY "stock_embeddings_read_all" ON public.stock_embeddings
  FOR SELECT USING (true);


-- =============================================================================
-- 2. News embeddings — rolling window of recent headlines
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.news_embeddings (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  content_hash  text UNIQUE NOT NULL,         -- sha256 of headline+source → dedupes
  headline      text NOT NULL,
  source        text,
  url           text,
  scope         text,                          -- 'stock_specific' | 'macro' | 'global'
  scope_ticker  text,                          -- when scope = 'stock_specific'
  country       text,                          -- when scope = 'global'
  embedding     vector(1536),
  published_at  timestamptz,
  created_at    timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS news_embeddings_hnsw_idx
  ON public.news_embeddings
  USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS news_embeddings_created_idx
  ON public.news_embeddings (created_at DESC);

ALTER TABLE public.news_embeddings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "news_embeddings_read_all" ON public.news_embeddings;
CREATE POLICY "news_embeddings_read_all" ON public.news_embeddings
  FOR SELECT USING (true);


-- =============================================================================
-- 3. RPC: semantic news matcher for a user's ticker universe
-- =============================================================================
-- Returns top-N news items semantically similar to ANY of the user's stocks,
-- within the recency window. The trick that gives us the "renewable energy
-- subsidy news → TATAPOWER affected" wedge: each news vector is compared
-- against EACH user stock vector, so news matches the closest stock regardless
-- of whether that ticker is named in the headline.
-- =============================================================================
CREATE OR REPLACE FUNCTION public.match_news_for_tickers(
  ticker_list      text[],
  match_count      int   DEFAULT 30,
  recency_hours    int   DEFAULT 48,
  match_threshold  float DEFAULT 0.55
)
RETURNS TABLE (
  id                uuid,
  headline          text,
  source            text,
  url               text,
  scope             text,
  scope_ticker      text,
  country           text,
  published_at      timestamptz,
  affected_ticker   text,
  similarity        float
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
  RETURN QUERY
  WITH user_stocks AS (
    SELECT s.ticker, s.embedding
    FROM public.stock_embeddings s
    WHERE s.ticker = ANY(ticker_list)
      AND s.embedding IS NOT NULL
  ),
  candidate_news AS (
    SELECT n.id, n.headline, n.source, n.url, n.scope, n.scope_ticker,
           n.country, n.published_at, n.embedding
    FROM public.news_embeddings n
    WHERE n.created_at > now() - (recency_hours || ' hours')::interval
      AND n.embedding IS NOT NULL
  ),
  -- For each news item, find its BEST-matching user stock.
  best_per_news AS (
    SELECT DISTINCT ON (cn.id)
      cn.id,
      cn.headline,
      cn.source,
      cn.url,
      cn.scope,
      cn.scope_ticker,
      cn.country,
      cn.published_at,
      us.ticker AS affected_ticker,
      1 - (cn.embedding <=> us.embedding) AS similarity
    FROM candidate_news cn
    CROSS JOIN user_stocks us
    ORDER BY cn.id, (cn.embedding <=> us.embedding) ASC
  )
  SELECT *
  FROM best_per_news bpn
  WHERE bpn.similarity > match_threshold
  ORDER BY bpn.similarity DESC
  LIMIT match_count;
END;
$$;

-- Allow authenticated users to invoke the RPC.
GRANT EXECUTE ON FUNCTION public.match_news_for_tickers(text[], int, int, float)
  TO anon, authenticated, service_role;


-- =============================================================================
-- 4. VERIFY (run these after migration succeeds)
-- =============================================================================
-- Confirm extension + tables + indexes exist:
--   SELECT extname FROM pg_extension WHERE extname = 'vector';
--   SELECT tablename FROM pg_tables WHERE tablename LIKE '%_embeddings';
--   SELECT indexname FROM pg_indexes WHERE tablename LIKE '%_embeddings';
--
-- Tables will be empty until the backend backfill runs:
--   POST /api/embeddings/backfill-stocks       (one-time, ~30s)
--   News embeddings populate as news is fetched (automatic).
-- =============================================================================
