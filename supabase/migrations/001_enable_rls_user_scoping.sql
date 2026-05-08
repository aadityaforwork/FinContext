-- =============================================================================
-- FinContext — Enable Row-Level Security on watchlist + portfolio
-- =============================================================================
-- Run this in the Supabase SQL Editor (Dashboard → SQL → New Query).
--
-- What this does:
--   1. Adds user_id (uuid, references auth.users) if missing on both tables.
--   2. Backfills NULL user_ids — old/orphan rows are deleted because they
--      cannot safely be attributed to any user.
--   3. Makes user_id NOT NULL with default = auth.uid() so future inserts
--      from the client SDK are auto-tagged with the signed-in user.
--   4. Enables Row-Level Security and adds policies so each user can only
--      SELECT/INSERT/UPDATE/DELETE their own rows.
--   5. Adds a unique index on (user_id, ticker) so upserts with
--      onConflict: "ticker,user_id" work correctly.
--
-- Idempotent: safe to run more than once.
-- =============================================================================

-- ----------- WATCHLIST ----------------------------------------------------------
ALTER TABLE public.watchlist
  ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE;

-- Drop orphan rows (no owner). These are the rows everyone could see.
DELETE FROM public.watchlist WHERE user_id IS NULL;

ALTER TABLE public.watchlist
  ALTER COLUMN user_id SET NOT NULL,
  ALTER COLUMN user_id SET DEFAULT auth.uid();

CREATE UNIQUE INDEX IF NOT EXISTS watchlist_user_ticker_uidx
  ON public.watchlist (user_id, ticker);

ALTER TABLE public.watchlist ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.watchlist FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "watchlist_select_own" ON public.watchlist;
DROP POLICY IF EXISTS "watchlist_insert_own" ON public.watchlist;
DROP POLICY IF EXISTS "watchlist_update_own" ON public.watchlist;
DROP POLICY IF EXISTS "watchlist_delete_own" ON public.watchlist;

CREATE POLICY "watchlist_select_own" ON public.watchlist
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "watchlist_insert_own" ON public.watchlist
  FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "watchlist_update_own" ON public.watchlist
  FOR UPDATE USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE POLICY "watchlist_delete_own" ON public.watchlist
  FOR DELETE USING (auth.uid() = user_id);


-- ----------- PORTFOLIO ----------------------------------------------------------
ALTER TABLE public.portfolio
  ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE;

DELETE FROM public.portfolio WHERE user_id IS NULL;

ALTER TABLE public.portfolio
  ALTER COLUMN user_id SET NOT NULL,
  ALTER COLUMN user_id SET DEFAULT auth.uid();

CREATE UNIQUE INDEX IF NOT EXISTS portfolio_user_ticker_uidx
  ON public.portfolio (user_id, ticker);

ALTER TABLE public.portfolio ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.portfolio FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "portfolio_select_own" ON public.portfolio;
DROP POLICY IF EXISTS "portfolio_insert_own" ON public.portfolio;
DROP POLICY IF EXISTS "portfolio_update_own" ON public.portfolio;
DROP POLICY IF EXISTS "portfolio_delete_own" ON public.portfolio;

CREATE POLICY "portfolio_select_own" ON public.portfolio
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "portfolio_insert_own" ON public.portfolio
  FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "portfolio_update_own" ON public.portfolio
  FOR UPDATE USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE POLICY "portfolio_delete_own" ON public.portfolio
  FOR DELETE USING (auth.uid() = user_id);


-- ----------- VERIFY ------------------------------------------------------------
-- After running, both tables should report rowsecurity = true:
--   SELECT relname, relrowsecurity FROM pg_class
--   WHERE relname IN ('watchlist','portfolio');
--
-- And four policies each:
--   SELECT tablename, policyname FROM pg_policies
--   WHERE tablename IN ('watchlist','portfolio');
-- =============================================================================
