-- =============================================================================
-- FinContext — Telegram bot link tables
-- =============================================================================
-- Powers the Telegram bot v0. Two small tables:
--
--   telegram_link_codes  — short-lived 6-char codes generated in the web app
--                           Settings page. The user pastes the code into the
--                           Telegram chat (`/link 123456`) to bind their chat
--                           to their FinContext account.
--
--   telegram_links       — durable 1:1 mapping user_id ↔ chat_id, used by the
--                           daily brief cron to know where to send each user's
--                           personalized morning brief.
--
-- Both tables are written via the service-role key from the backend, so RLS
-- denies all anon access by default. Re-runs are safe (IF NOT EXISTS).
--
-- Run AFTER 005_fix_dedup_constraint.sql.
-- Paste into Supabase SQL Editor → Run.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- telegram_link_codes — short-lived linking codes
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.telegram_link_codes (
  code         text PRIMARY KEY,                  -- 6-char uppercase alnum
  user_id      uuid NOT NULL,                     -- FROM auth.users; not FK to allow CASCADE flexibility
  expires_at   timestamptz NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS telegram_link_codes_user_idx
  ON public.telegram_link_codes(user_id);
CREATE INDEX IF NOT EXISTS telegram_link_codes_expires_idx
  ON public.telegram_link_codes(expires_at);

-- ---------------------------------------------------------------------------
-- telegram_links — durable user ↔ chat mapping
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.telegram_links (
  user_id            uuid PRIMARY KEY,            -- one Telegram chat per FC account
  telegram_chat_id   bigint NOT NULL UNIQUE,      -- one FC account per chat
  telegram_username  text,                        -- snapshot for diagnostics; not auth-bearing
  linked_at          timestamptz NOT NULL DEFAULT now(),
  daily_brief_enabled boolean NOT NULL DEFAULT true,
  last_brief_sent_at timestamptz
);

CREATE INDEX IF NOT EXISTS telegram_links_chat_idx
  ON public.telegram_links(telegram_chat_id);

-- ---------------------------------------------------------------------------
-- RLS — service role only. The bot runs server-side; no anon/auth access.
-- ---------------------------------------------------------------------------
ALTER TABLE public.telegram_link_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.telegram_links      ENABLE ROW LEVEL SECURITY;

-- No SELECT/INSERT/UPDATE/DELETE policies for anon or authenticated. The
-- service-role key bypasses RLS, so backend writes work; everything else is
-- locked down by default. If you later want users to view their own link in
-- the UI, add a policy: CREATE POLICY "self select" ON telegram_links
--   FOR SELECT USING (auth.uid() = user_id);

-- VERIFY:
--   SELECT count(*) FROM public.telegram_link_codes;
--   SELECT count(*) FROM public.telegram_links;
-- =============================================================================
