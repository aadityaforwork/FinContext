-- =============================================================================
-- FinContext — grounding-contract feedback loop
-- =============================================================================
-- Adds the fast, deterministic sibling to the market-outcome loop:
--
--   prompt_call_log     exact private transcript + all grounding scores
--   grounding_fixtures  one lightweight row per violated contract rule
--   grounding_alert_log aggregate threshold crossings consumed by the drafter
--
-- The transcript deliberately stays in prompt_call_log. ai_predictions is
-- publicly readable and must never receive a real user's CONTEXT or completion;
-- both new tables are private (RLS on, no policies) and grounding_fixtures only
-- references the private transcript instead of copying it.
--
-- Run AFTER 015_per_ticker_hit_threshold.sql. Safe to re-run.
-- =============================================================================

ALTER TABLE public.prompt_call_log
  ADD COLUMN IF NOT EXISTS observation_id text,
  ADD COLUMN IF NOT EXISTS task_text text,
  ADD COLUMN IF NOT EXISTS schema_description text,
  ADD COLUMN IF NOT EXISTS output_snapshot jsonb,
  ADD COLUMN IF NOT EXISTS grounding_scores jsonb;

CREATE INDEX IF NOT EXISTS prompt_call_log_grounding_created_idx
  ON public.prompt_call_log (prompt_name, created_at DESC)
  WHERE grounding_scores IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.grounding_fixtures (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at        timestamptz NOT NULL DEFAULT now(),
  call_id           uuid NOT NULL REFERENCES public.prompt_call_log(id) ON DELETE CASCADE,
  prompt_name       text NOT NULL,
  violation_type    text NOT NULL,
  score_value       numeric NOT NULL,
  violation_detail text
);

ALTER TABLE public.grounding_fixtures
  DROP CONSTRAINT IF EXISTS grounding_fixtures_call_violation_unique;
ALTER TABLE public.grounding_fixtures
  ADD CONSTRAINT grounding_fixtures_call_violation_unique
  UNIQUE (call_id, violation_type);

CREATE INDEX IF NOT EXISTS grounding_fixtures_prompt_violation_created_idx
  ON public.grounding_fixtures (prompt_name, violation_type, created_at DESC);

ALTER TABLE public.grounding_fixtures ENABLE ROW LEVEL SECURITY;
-- No policies: service-role only. The referenced transcript is private too.

CREATE TABLE IF NOT EXISTS public.grounding_alert_log (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at         timestamptz NOT NULL DEFAULT now(),
  prompt_name        text NOT NULL,
  violation_type     text NOT NULL,
  recent_n           int NOT NULL,
  failure_n          int NOT NULL,
  failure_rate_pct   numeric NOT NULL,
  threshold_pct      numeric NOT NULL,
  message            text NOT NULL
);

CREATE INDEX IF NOT EXISTS grounding_alert_log_prompt_violation_created_idx
  ON public.grounding_alert_log (prompt_name, violation_type, created_at DESC);

ALTER TABLE public.grounding_alert_log ENABLE ROW LEVEL SECURITY;
-- No policies: service-role only.

ALTER TABLE public.prompt_draft_runs
  ADD COLUMN IF NOT EXISTS trigger_type text NOT NULL DEFAULT 'accuracy',
  ADD COLUMN IF NOT EXISTS trigger_key text;

-- VERIFY:
--   SELECT prompt_name, grounding_scores, created_at
--     FROM public.prompt_call_log WHERE grounding_scores IS NOT NULL
--     ORDER BY created_at DESC LIMIT 10;
--   SELECT prompt_name, violation_type, count(*)
--     FROM public.grounding_fixtures GROUP BY 1,2 ORDER BY 1,2;
-- =============================================================================
