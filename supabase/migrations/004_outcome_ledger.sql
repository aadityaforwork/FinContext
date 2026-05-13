-- =============================================================================
-- FinContext — outcome ledger
-- =============================================================================
-- Tracks every forward-looking AI prediction the system makes (Tomorrow's
-- per-holding watch items + News Impact items) and records whether the
-- predicted direction matched the actual price move 1d / 5d / 20d later.
--
-- Powers the public /accuracy page that shows hit-rate over time, broken
-- down by source / impact / catalyst — the credibility moat.
--
-- Run AFTER 003_stock_tags.sql.
-- Paste into Supabase SQL Editor → Run.
-- Safe to re-run.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- ai_predictions — one row per forward-looking AI call
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.ai_predictions (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ticker          text NOT NULL,
  prediction_date date NOT NULL,
  source          text NOT NULL,                 -- 'tomorrow_per_holding' | 'news_feed'
  impact_level    text,                          -- 'high' | 'medium' | 'low'
  direction       text NOT NULL,                 -- 'positive' | 'negative' | 'neutral' | 'mixed'
  catalyst_type   text,                          -- 'earnings' | 'news' | 'technical' | 'sector_flow' | 'macro' | 'stock_specific'
  reason          text,
  cited_sources   text[] DEFAULT '{}',
  technical_state jsonb,
  price_at_call   numeric,                       -- close price at prediction_date close
  -- Dedup key — for news_feed: news_feed:{ticker}:{news_id}:{date}
  --             for tomorrow:  tomorrow:{ticker}:{date}
  -- Lets us UPSERT instead of accumulating duplicates when the same call is
  -- generated multiple times in a day (e.g. 10 users load the dashboard).
  dedup_key       text,
  metadata        jsonb,
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ai_predictions_date_idx
  ON public.ai_predictions(prediction_date DESC);
CREATE INDEX IF NOT EXISTS ai_predictions_ticker_date_idx
  ON public.ai_predictions(ticker, prediction_date DESC);
CREATE INDEX IF NOT EXISTS ai_predictions_source_idx
  ON public.ai_predictions(source);

-- Real UNIQUE constraint (not a partial index) — required for PostgREST's
-- `?on_conflict=dedup_key` upsert. Multiple NULLs are allowed in a UNIQUE
-- constraint by default, so dedup_key NULL = no dedup (intended for hand-
-- inserted rows that don't go through log_predictions).
ALTER TABLE public.ai_predictions
  DROP CONSTRAINT IF EXISTS ai_predictions_dedup_key_unique;
ALTER TABLE public.ai_predictions
  ADD CONSTRAINT ai_predictions_dedup_key_unique UNIQUE (dedup_key);

-- ---------------------------------------------------------------------------
-- prediction_outcomes — one row per (prediction, horizon) pair
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.prediction_outcomes (
  prediction_id     uuid REFERENCES public.ai_predictions(id) ON DELETE CASCADE,
  horizon           text NOT NULL,             -- '1d' | '5d' | '20d'
  price_at_horizon  numeric,
  return_pct        numeric,
  hit               boolean,                   -- direction matched + magnitude threshold
  computed_at       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (prediction_id, horizon)
);

CREATE INDEX IF NOT EXISTS prediction_outcomes_hit_idx
  ON public.prediction_outcomes(hit);
CREATE INDEX IF NOT EXISTS prediction_outcomes_horizon_idx
  ON public.prediction_outcomes(horizon);

-- ---------------------------------------------------------------------------
-- prediction_results — joined view used by the Accuracy endpoints
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.prediction_results AS
SELECT
  p.id,
  p.ticker,
  p.prediction_date,
  p.source,
  p.impact_level,
  p.direction,
  p.catalyst_type,
  p.reason,
  p.cited_sources,
  p.technical_state,
  p.price_at_call,
  p.created_at,
  o.horizon,
  o.price_at_horizon,
  o.return_pct,
  o.hit
FROM public.ai_predictions p
LEFT JOIN public.prediction_outcomes o ON o.prediction_id = p.id;

-- ---------------------------------------------------------------------------
-- RLS — backend writes through service_role (bypasses RLS); anon may SELECT
-- because the Accuracy page is intentionally public.
-- ---------------------------------------------------------------------------
ALTER TABLE public.ai_predictions      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.prediction_outcomes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "anon select" ON public.ai_predictions;
CREATE POLICY "anon select" ON public.ai_predictions FOR SELECT USING (true);

DROP POLICY IF EXISTS "anon select" ON public.prediction_outcomes;
CREATE POLICY "anon select" ON public.prediction_outcomes FOR SELECT USING (true);

-- VERIFY:
--   SELECT count(*) FROM public.ai_predictions;
--   SELECT count(*) FROM public.prediction_outcomes;
--   SELECT * FROM public.prediction_results LIMIT 5;
-- =============================================================================
