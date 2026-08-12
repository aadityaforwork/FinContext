-- =============================================================================
-- FinContext — prompt call log
-- =============================================================================
-- Path-back leg 3b, Phase 3 (online monitor). One row per
-- ai_client.generate_grounded_json() call made through a Langfuse-managed
-- prompt (portfolio.tomorrow_watch / portfolio.news_feed_annotation today —
-- see prompt_registry.py's module docstring for why only these two).
--
-- Deliberately CALL-grained, not prediction-grained: a single call can
-- produce many ai_predictions rows (e.g. 15 per_holding items from one
-- tomorrow-watch call), and a call that fails to parse produces ZERO
-- ai_predictions rows at all — so ai_predictions structurally cannot
-- represent "how often does this prompt version fail to produce valid
-- JSON", which is exactly the schema_validation_failure_rate metric
-- prompt_monitor.py needs. This table exists to make every attempted call
-- visible, success or failure, independent of how many (if any) downstream
-- prediction rows it produced.
--
-- No user_id / no RLS "anon select" policy — this is pure system telemetry
-- (prompt performance), not user data, same precedent as ai_predictions/
-- prediction_outcomes being global rather than per-user tables. Written
-- only via the backend's service-role client (see outcome_ledger.py
-- log_call_metrics/call_metrics_rows); RLS is enabled with no policies so
-- even an anon/authenticated Supabase key gets nothing back by default.
--
-- Run AFTER 007_peer_pulse.sql.
-- Paste into Supabase SQL Editor → Run. Safe to re-run.
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.prompt_call_log (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at        timestamptz NOT NULL DEFAULT now(),
  prompt_name       text NOT NULL,           -- e.g. 'portfolio.tomorrow_watch'
  prompt_version    int,                     -- NULL when prompt_source != 'langfuse' (fallback text has no version)
  prompt_source     text NOT NULL,           -- 'langfuse' | 'fallback_no_client' | 'fallback_sdk' | 'fallback_error'
  confidence        text,                    -- 'low' | 'medium' | 'high' | NULL (prompt's schema may not have this field)
  data_gaps_count   int,                     -- length of the response's data_gaps[] array, NULL if unparseable
  parse_error       boolean NOT NULL DEFAULT false,  -- true when the response failed to parse as JSON
  tokens_in         int,
  tokens_out        int,
  duration_ms       numeric
);

CREATE INDEX IF NOT EXISTS prompt_call_log_name_version_created_idx
  ON public.prompt_call_log (prompt_name, prompt_version, created_at DESC);

ALTER TABLE public.prompt_call_log ENABLE ROW LEVEL SECURITY;
-- No policies added — service-role (backend) bypasses RLS for writes/reads;
-- everyone else gets zero rows. Intentionally NOT public like ai_predictions.

-- VERIFY:
--   SELECT count(*) FROM public.prompt_call_log;
--   SELECT prompt_name, prompt_version, count(*) FROM public.prompt_call_log GROUP BY 1,2 ORDER BY 1,2;
-- =============================================================================
