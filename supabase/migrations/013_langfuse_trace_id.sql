-- 013_langfuse_trace_id.sql
-- ---------------------------------------------------------------------------
-- Adds the join key between a logged LLM call and its Langfuse trace.
--
-- WHY: until now the quality verdict for a prompt version lived only in this
-- database (prompt_call_log + prediction_outcomes, read by prompt_monitor.py)
-- while the prompt versions themselves live in Langfuse. Nothing connected the
-- two, so Langfuse could show cost and latency per version but never whether a
-- version was any GOOD. Storing the trace id lets the daily outcome job push
-- the market's grade back onto the exact generation that made the call — see
-- outcome_ledger._push_outcome_scores() and services/langfuse_scores.py.
--
-- ai_predictions deliberately does NOT get a column here: it already has a
-- jsonb `metadata` column, and the trace id goes in as
-- metadata->>'langfuse_trace_id'. A Langfuse trace id is safe in that
-- world-readable table (AGENTS.md rule 9 — it has a public "anon select"
-- policy) for the same reason call_id already is: it is an opaque handle that
-- resolves to nothing without separate Langfuse credentials.
--
-- Nullable with no backfill: every row written before this migration simply
-- has no trace to point at, and the outcome pusher skips those rather than
-- guessing.
-- ---------------------------------------------------------------------------

alter table public.prompt_call_log
  add column if not exists trace_id text;

comment on column public.prompt_call_log.trace_id is
  'Langfuse trace id for this LLM call (llm_trace span). Join key for pushing '
  'delayed market-outcome scores back onto the generation, and for opening a '
  'logged call as a trace without searching. NULL for rows predating migration 013.';

-- Lookups are "given this trace, find the call row" during debugging, and
-- "find rows that have a trace at all" when backfilling scores. Partial index
-- keeps it small — most historical rows are NULL and never queried.
create index if not exists prompt_call_log_trace_id_idx
  on public.prompt_call_log (trace_id)
  where trace_id is not null;
