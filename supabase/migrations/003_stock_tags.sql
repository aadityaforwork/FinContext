-- =============================================================================
-- FinContext — stock_embeddings tags column
-- =============================================================================
-- Adds a `tags` text[] column to stock_embeddings so the catalog can carry
-- theme tags ("renewables", "exports", "govt_psu", etc.) alongside the vector.
-- Tags make semantic retrieval sharper and enable hard-filter queries later
-- (e.g. "find all news affecting any of my govt_psu holdings").
--
-- Run AFTER 002_pgvector_semantic_news.sql.
-- Paste into Supabase SQL Editor → Run.
-- Safe to re-run.
-- =============================================================================

ALTER TABLE public.stock_embeddings
  ADD COLUMN IF NOT EXISTS tags text[] DEFAULT '{}';

-- GIN index for fast `tags @> ARRAY['theme']` lookups.
CREATE INDEX IF NOT EXISTS stock_embeddings_tags_gin_idx
  ON public.stock_embeddings
  USING gin (tags);

-- VERIFY:
--   SELECT column_name, data_type FROM information_schema.columns
--   WHERE table_name = 'stock_embeddings' AND column_name = 'tags';
-- Should return: tags | ARRAY
-- =============================================================================
