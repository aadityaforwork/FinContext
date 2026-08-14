-- =============================================================================
-- FinContext — miss fixtures
-- =============================================================================
-- Path-back leg 3d: miss_fixtures.py. Two changes:
--
-- (1) prompt_call_log gains `context_snapshot` — the exact CONTEXT dict
--     passed to generate_grounded_json for that call. This is the ONLY
--     place a call's raw context (real portfolio holdings, watchlist,
--     headlines) is ever persisted. It must NEVER be added to
--     ai_predictions.metadata instead — ai_predictions has a public
--     "anon select" RLS policy (migration 004, `USING (true)`) because the
--     Accuracy page is intentionally public; prompt_call_log has no such
--     policy (service-role only). See outcome_ledger.log_call_metrics'
--     docstring and AGENTS.md rule 9.
--
-- (2) `miss_fixtures` — one row per market-graded miss that's been
--     converted into a permanent eval fixture: the exact context that was
--     live at prediction time (via prompt_call_log.context_snapshot, found
--     by ai_predictions.metadata.call_id) plus the market's own graded
--     "correct" direction as ground truth. eval_runner.py /
--     prompt_gate.py can run these forever after, the same way a
--     hand-written case in app/services/prompt_eval_cases.py does — except these come
--     from real misses instead of a human authoring one. See
--     miss_fixtures.py's module docstring for the full design.
--
-- Same private trust boundary as prompt_call_log/accuracy_alert_log — RLS
-- enabled, no policies, service-role only. context_snapshot here is exactly
-- as sensitive as the one on prompt_call_log (it's a copy of the same
-- data), so this table gets the identical treatment.
--
-- Run AFTER 009_accuracy_alert_log.sql.
-- Paste into Supabase SQL Editor → Run. Safe to re-run.
-- =============================================================================

ALTER TABLE public.prompt_call_log
  ADD COLUMN IF NOT EXISTS context_snapshot jsonb;

CREATE TABLE IF NOT EXISTS public.miss_fixtures (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at          timestamptz NOT NULL DEFAULT now(),
  prediction_id       uuid NOT NULL REFERENCES public.ai_predictions(id) ON DELETE CASCADE,
  prompt_name         text NOT NULL,           -- e.g. 'portfolio.tomorrow_watch'
  ticker              text NOT NULL,
  prediction_date     date NOT NULL,
  catalyst_type       text,
  original_direction  text NOT NULL,           -- what the model predicted (the miss)
  expected_direction  text NOT NULL,           -- what the market actually did (ground truth)
  reason              text,                    -- original claim text, for a human skimming fixtures
  return_pct          numeric NOT NULL,
  context_snapshot    jsonb NOT NULL           -- the exact context the fixture replays
);

-- One fixture per prediction — the idempotency key for the daily converter
-- job (log_miss_fixture's duplicate-key path is a designed no-op, not an
-- error).
ALTER TABLE public.miss_fixtures
  DROP CONSTRAINT IF EXISTS miss_fixtures_prediction_id_unique;
ALTER TABLE public.miss_fixtures
  ADD CONSTRAINT miss_fixtures_prediction_id_unique UNIQUE (prediction_id);

CREATE INDEX IF NOT EXISTS miss_fixtures_prompt_name_created_idx
  ON public.miss_fixtures (prompt_name, created_at DESC);

ALTER TABLE public.miss_fixtures ENABLE ROW LEVEL SECURITY;
-- No policies added — service-role (backend) bypasses RLS for writes/reads;
-- everyone else gets zero rows.

-- VERIFY:
--   SELECT count(*) FROM public.miss_fixtures;
--   SELECT prompt_name, ticker, original_direction, expected_direction, return_pct
--     FROM public.miss_fixtures ORDER BY created_at DESC LIMIT 20;
--   SELECT count(*) FROM public.prompt_call_log WHERE context_snapshot IS NOT NULL;
-- =============================================================================
