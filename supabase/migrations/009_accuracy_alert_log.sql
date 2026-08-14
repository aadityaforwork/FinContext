-- =============================================================================
-- FinContext — accuracy alert log
-- =============================================================================
-- Path-back leg 3c: accuracy_monitor.py. One row per accuracy-drift alert
-- actually FIRED (not every daily evaluation — only the ones that crossed
-- both the sample-size and effect-size thresholds), for a `source`
-- (tomorrow_per_holding | news_feed), which maps 1:1 onto a Langfuse-managed
-- prompt (see accuracy_monitor.py's SOURCE_TO_PROMPT).
--
-- Two jobs: (1) permanent audit trail of every alert this system has ever
-- sent, (2) the read side (outcome_ledger.last_accuracy_alert) drives the
-- alert cooldown so a segment that's still degraded tomorrow doesn't fire a
-- second Telegram message tomorrow too.
--
-- This module only ever ALERTS — it never reverts, promotes, or edits a
-- prompt. A market-graded hit-rate drop can come from a genuine regime
-- change, not just a bad prompt edit; that judgment call stays human. See
-- accuracy_monitor.py's module docstring.
--
-- No user_id / no RLS "anon select" policy — system telemetry, not user
-- data, same precedent as prompt_call_log (migration 008). Written only via
-- the backend's service-role client; RLS is enabled with no policies so an
-- anon/authenticated Supabase key gets nothing back by default.
--
-- Run AFTER 008_prompt_call_log.sql.
-- Paste into Supabase SQL Editor → Run. Safe to re-run.
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.accuracy_alert_log (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at             timestamptz NOT NULL DEFAULT now(),
  source                 text NOT NULL,           -- 'tomorrow_per_holding' | 'news_feed'
  prompt_name            text,                     -- e.g. 'portfolio.tomorrow_watch' — NULL only if SOURCE_TO_PROMPT is ever out of sync
  recent_n               int NOT NULL,
  recent_hit_rate_pct    numeric NOT NULL,
  baseline_n             int NOT NULL,
  baseline_hit_rate_pct  numeric NOT NULL,
  drop_pp                numeric NOT NULL,         -- baseline_hit_rate_pct - recent_hit_rate_pct
  message                text NOT NULL             -- the exact text sent to Telegram, for audit
);

CREATE INDEX IF NOT EXISTS accuracy_alert_log_source_created_idx
  ON public.accuracy_alert_log (source, created_at DESC);

ALTER TABLE public.accuracy_alert_log ENABLE ROW LEVEL SECURITY;
-- No policies added — service-role (backend) bypasses RLS for writes/reads;
-- everyone else gets zero rows.

-- VERIFY:
--   SELECT count(*) FROM public.accuracy_alert_log;
--   SELECT source, created_at, drop_pp FROM public.accuracy_alert_log ORDER BY created_at DESC LIMIT 20;
-- =============================================================================
