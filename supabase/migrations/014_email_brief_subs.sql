-- FinContext - email daily brief subscriptions
--
-- The Telegram brief keys off `telegram_links`. Email needs its own table so a
-- user can get one channel without the other, and so we can store the address
-- we actually send to rather than re-reading auth.users on every cron run.
--
-- Written via the service-role key from the backend, so RLS denies all anon
-- access by default. Re-runs are safe (IF NOT EXISTS).
--
-- Run AFTER 013_langfuse_trace_id.sql.
-- Paste into Supabase SQL Editor -> Run.

CREATE TABLE IF NOT EXISTS public.email_brief_subs (
  user_id             uuid PRIMARY KEY,           -- FROM auth.users; not FK, matches telegram_links
  email               text NOT NULL,              -- snapshot at subscribe time
  enabled             boolean NOT NULL DEFAULT true,
  unsubscribe_token   text NOT NULL UNIQUE,       -- url-safe, powers one-click unsubscribe
  subscribed_at       timestamptz NOT NULL DEFAULT now(),
  last_brief_sent_at  timestamptz,
  last_error          text                        -- last send failure, for triage
);

CREATE INDEX IF NOT EXISTS email_brief_subs_enabled_idx
  ON public.email_brief_subs(enabled);
CREATE INDEX IF NOT EXISTS email_brief_subs_token_idx
  ON public.email_brief_subs(unsubscribe_token);

ALTER TABLE public.email_brief_subs ENABLE ROW LEVEL SECURITY;

-- No policies for anon or authenticated. The backend uses the service-role
-- key, which bypasses RLS; the unsubscribe link goes through the backend too,
-- so the token never needs direct table access.

-- VERIFY:
--   SELECT count(*) FROM public.email_brief_subs;
