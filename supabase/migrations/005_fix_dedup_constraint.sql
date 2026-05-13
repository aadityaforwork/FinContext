-- =============================================================================
-- FinContext — fix ai_predictions.dedup_key constraint for upsert
-- =============================================================================
-- 004 created `dedup_key` as a PARTIAL unique index (WHERE dedup_key IS NOT NULL).
-- PostgREST's `?on_conflict=dedup_key` parameter requires a real UNIQUE
-- constraint or a non-partial unique index — partial indexes throw:
--
--   "there is no unique or exclusion constraint matching the ON CONFLICT
--    specification" (SQLSTATE 42P10)
--
-- This migration drops the partial index and replaces it with a regular
-- UNIQUE constraint. Postgres allows multiple NULLs in a UNIQUE constraint by
-- default, so the semantics are identical to the partial index for our case
-- (dedup_key NULL = no dedup, e.g. for hand-inserted rows).
--
-- Run this AFTER 004_outcome_ledger.sql.
-- Paste into Supabase SQL Editor → Run.
-- Safe to re-run.
-- =============================================================================

DROP INDEX IF EXISTS public.ai_predictions_dedup_uidx;

ALTER TABLE public.ai_predictions
  DROP CONSTRAINT IF EXISTS ai_predictions_dedup_key_unique;

ALTER TABLE public.ai_predictions
  ADD CONSTRAINT ai_predictions_dedup_key_unique UNIQUE (dedup_key);

-- VERIFY:
--   SELECT conname, contype FROM pg_constraint
--   WHERE conrelid = 'public.ai_predictions'::regclass AND contype = 'u';
-- Should include: ai_predictions_dedup_key_unique | u
-- =============================================================================
