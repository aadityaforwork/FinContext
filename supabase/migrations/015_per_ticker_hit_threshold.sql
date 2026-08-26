-- =============================================================================
-- 015 — Record the hit threshold each outcome was graded against
-- =============================================================================
-- WHY
-- ---
-- Until 2026-08-25 the grading bar was one number for every stock at a given
-- horizon (0.5% * sqrt(trading days), migration 012). That is fair across
-- horizons but NOT across stocks: clearing 0.5% is nothing for a 3%-daily-sigma
-- name and a genuine move for a 1%-sigma one. Measured on this table's 1621
-- graded rows, a no-skill "always positive" guess scored:
--
--     top-third-sigma stocks   43.4%      <- volatile names handed free hits
--     bottom-third-sigma       30.4%
--     ------------------------------
--     difficulty gap           13.0pp at 1d, from volatility alone
--
-- So a big part of the /accuracy hit rate was measuring which stocks the model
-- happened to talk about, not whether it was right. The code fix is
-- outcome_ledger.hit_threshold_pct(horizon, sigma_daily_pct):
--
--     threshold = 0.32 * sigma_ticker_daily * sqrt(trading days)
--
-- which closes that 13.0pp gap to 0.6pp at 1d.
--
-- WHY THIS MIGRATION ADDS COLUMNS INSTEAD OF RE-GRADING IN SQL
-- ------------------------------------------------------------
-- Migration 012 could recompute `hit` in pure SQL because the old threshold
-- was a function of stored columns only (direction, return_pct, horizon).
-- That is no longer true: the new threshold depends on the ticker's trailing
-- 60-trading-day volatility AS OF THE PREDICTION DATE — data that lives in
-- yfinance, not in Postgres, and that changes as time passes. Re-deriving it
-- later would silently grade an old call against today's volatility.
--
-- So the threshold stops being derivable and becomes a stored fact. Every row
-- records the bar it was actually judged against, which also means a table
-- holding both old flat-graded and new sigma-graded rows stays auditable
-- instead of being silently inconsistent (`threshold_basis` says which).
--
-- Existing rows get NULLs and keep their current `hit` value. They are NOT
-- re-graded here — that needs price history, so it is a Python backfill
-- (scripts/regrade_outcomes.py), run deliberately, not a side effect of
-- applying a migration.
--
-- Safe to re-run. Adds columns only; touches no existing value.
-- =============================================================================

ALTER TABLE public.prediction_outcomes
  ADD COLUMN IF NOT EXISTS hit_threshold_pct numeric,
  ADD COLUMN IF NOT EXISTS sigma_daily_pct   numeric,
  ADD COLUMN IF NOT EXISTS threshold_basis   text;

COMMENT ON COLUMN public.prediction_outcomes.hit_threshold_pct IS
  'The |return_pct| bar this row was graded against, in percent. Stored, not '
  'derived: it depends on the ticker''s volatility as of the prediction date.';
COMMENT ON COLUMN public.prediction_outcomes.sigma_daily_pct IS
  'Trailing 60-trading-day stdev of daily returns (percent) as of the '
  'prediction date, clamped to [0.4, 6.0]. NULL when unavailable at grade time.';
COMMENT ON COLUMN public.prediction_outcomes.threshold_basis IS
  '''sigma'' = graded on the per-ticker rule; ''flat'' = fell back to the '
  'horizon-only band because sigma could not be estimated; NULL = graded '
  'before migration 015 and never backfilled.';

-- Lets the accuracy endpoints report "how much of this table is on the new
-- rule yet" without a sequential scan once the backfill starts.
CREATE INDEX IF NOT EXISTS prediction_outcomes_threshold_basis_idx
  ON public.prediction_outcomes(threshold_basis);

-- ---------------------------------------------------------------------------
-- Re-create the public view so the Accuracy page can state the real bar each
-- call was judged against, per row, instead of quoting one global number that
-- is no longer true for any particular stock.
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
  o.hit,
  o.hit_threshold_pct,
  o.sigma_daily_pct,
  o.threshold_basis
FROM public.ai_predictions p
LEFT JOIN public.prediction_outcomes o ON o.prediction_id = p.id;

-- VERIFY:
--   SELECT threshold_basis, count(*) FROM public.prediction_outcomes
--    GROUP BY 1;                      -- expect all NULL until the backfill runs
--   SELECT hit_threshold_pct, sigma_daily_pct, threshold_basis
--     FROM public.prediction_results LIMIT 5;
-- =============================================================================
