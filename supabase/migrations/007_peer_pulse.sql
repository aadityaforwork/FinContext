-- =============================================================================
-- FinContext — Peer Pulse support
-- =============================================================================
-- Adds `created_at` to portfolio + watchlist (with a default of now()) so the
-- peer-pulse endpoint can ask "what did similar users add in the last 7 days?"
-- and adds an index for that query.
--
-- Existing rows get `created_at = now()` on first run. That's a one-time
-- imprecision (they won't show up in the "last 7 days" window) but is
-- harmless — the cohort feature is forward-looking anyway.
--
-- Privacy: this migration does NOT relax any RLS policies. The aggregation
-- query runs from the backend using SUPABASE_SERVICE_KEY, never from a user's
-- session. Backend enforces k-anonymity (min 5 peers in cohort, min 2 distinct
-- adders per ticker) so no individual user's adds can be inferred.
--
-- Idempotent: safe to re-run.
-- =============================================================================

ALTER TABLE public.portfolio
  ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();

ALTER TABLE public.watchlist
  ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();

-- Index supports `.gte("created_at", cutoff)` lookups when fanning out across
-- many user_ids. The (created_at, user_id) order matters — the planner can
-- range-scan the timestamp portion, then probe by user_id.
CREATE INDEX IF NOT EXISTS portfolio_created_user_idx
  ON public.portfolio (created_at, user_id);

CREATE INDEX IF NOT EXISTS watchlist_created_user_idx
  ON public.watchlist (created_at, user_id);
