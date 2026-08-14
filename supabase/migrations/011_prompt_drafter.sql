-- =============================================================================
-- FinContext — prompt drafter (path-back leg 3e)
-- =============================================================================
-- Backs prompt_drafter.py — the LangGraph draft/test/approve agent. Two
-- tables:
--
-- (1) `prompt_draft_runs` — one row per draft attempt: which prompt, why it
--     was triggered (an accuracy_monitor.py alert), what the gate said, and
--     its current lifecycle status. Doubles as an audit trail AND the read
--     side that drives two things: (a) run_pending_drafts()'s cooldown so a
--     still-degraded segment doesn't get a fresh draft attempt every single
--     day, same "audit log doubles as query surface" pattern as
--     accuracy_alert_log; (b) check_pending_approvals()'s worklist of
--     threads currently paused waiting on a human.
--
-- (2) `prompt_draft_checkpoints` — one row per in-flight thread_id, holding
--     an opaque, pickled+base64 snapshot of that thread's LangGraph
--     checkpoint state (the actual `interrupt()` pause point). This is what
--     lets the agent's pause-for-a-human-mid-run survive across separate
--     HTTP requests days apart — see prompt_drafter.py's module docstring
--     for why a Supabase row (not LangGraph's own Postgres/Sqlite savers)
--     is the persistence layer here. `blob` is meaningless outside this
--     module; nothing about it is human-readable or queryable, which is
--     fine — prompt_draft_runs is the table a human actually reads.
--
-- Same private trust boundary as prompt_call_log/accuracy_alert_log/
-- miss_fixtures — RLS enabled, no policies, service-role only. Neither
-- table stores a real user's portfolio context (the checkpoint blob only
-- ever contains prompt text, gate-report numbers, and alert metadata — no
-- CONTEXT dict), so this is a stricter-than-required default, not a
-- rule-9-driven necessity, kept consistent with every other table in this
-- family regardless.
--
-- Run AFTER 010_miss_fixtures.sql.
-- Paste into Supabase SQL Editor → Run. Safe to re-run.
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.prompt_draft_runs (
  thread_id           text PRIMARY KEY,        -- LangGraph thread_id for this run
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  prompt_name         text NOT NULL,           -- e.g. 'portfolio.tomorrow_watch'
  trigger_reason      text NOT NULL,           -- the accuracy_monitor.py alert that started this run
  status              text NOT NULL,           -- running | blocked | no_change | awaiting_approval | promoted | expired | error
  baseline_version    integer,                 -- Langfuse `production` version this run compared against
  candidate_version   integer,                 -- Langfuse version created (labeled 'candidate'), if any
  gate_verdict        text                     -- BLOCK | IMPROVED | NO_CHANGE, from prompt_gate.py
);

CREATE INDEX IF NOT EXISTS prompt_draft_runs_prompt_created_idx
  ON public.prompt_draft_runs (prompt_name, created_at DESC);

CREATE INDEX IF NOT EXISTS prompt_draft_runs_status_idx
  ON public.prompt_draft_runs (status);

ALTER TABLE public.prompt_draft_runs ENABLE ROW LEVEL SECURITY;
-- No policies added — service-role (backend) bypasses RLS; everyone else
-- gets zero rows.

CREATE TABLE IF NOT EXISTS public.prompt_draft_checkpoints (
  thread_id   text PRIMARY KEY REFERENCES public.prompt_draft_runs(thread_id) ON DELETE CASCADE,
  updated_at  timestamptz NOT NULL DEFAULT now(),
  blob        text NOT NULL             -- base64(pickle(langgraph InMemorySaver thread slice))
);

ALTER TABLE public.prompt_draft_checkpoints ENABLE ROW LEVEL SECURITY;
-- No policies added — service-role only, same as above.

-- VERIFY:
--   SELECT thread_id, prompt_name, status, gate_verdict, created_at
--     FROM public.prompt_draft_runs ORDER BY created_at DESC LIMIT 20;
--   SELECT count(*) FROM public.prompt_draft_checkpoints;
-- =============================================================================
