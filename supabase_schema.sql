-- Run this in Supabase Dashboard → SQL Editor
-- Creates watchlist + portfolio tables with per-user RLS scoping.

-- ============ WATCHLIST ============
create table if not exists public.watchlist (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  ticker text not null,
  added_at timestamptz not null default now(),
  unique (user_id, ticker)
);

alter table public.watchlist enable row level security;

drop policy if exists "watchlist_select_own" on public.watchlist;
create policy "watchlist_select_own" on public.watchlist
  for select using (auth.uid() = user_id);

drop policy if exists "watchlist_insert_own" on public.watchlist;
create policy "watchlist_insert_own" on public.watchlist
  for insert with check (auth.uid() = user_id);

drop policy if exists "watchlist_update_own" on public.watchlist;
create policy "watchlist_update_own" on public.watchlist
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "watchlist_delete_own" on public.watchlist;
create policy "watchlist_delete_own" on public.watchlist
  for delete using (auth.uid() = user_id);

-- ============ PORTFOLIO ============
create table if not exists public.portfolio (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  ticker text not null,
  quantity numeric not null default 0,
  buy_price numeric not null default 0,
  added_at timestamptz not null default now(),
  unique (user_id, ticker)
);

alter table public.portfolio enable row level security;

drop policy if exists "portfolio_select_own" on public.portfolio;
create policy "portfolio_select_own" on public.portfolio
  for select using (auth.uid() = user_id);

drop policy if exists "portfolio_insert_own" on public.portfolio;
create policy "portfolio_insert_own" on public.portfolio
  for insert with check (auth.uid() = user_id);

drop policy if exists "portfolio_update_own" on public.portfolio;
create policy "portfolio_update_own" on public.portfolio
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "portfolio_delete_own" on public.portfolio;
create policy "portfolio_delete_own" on public.portfolio
  for delete using (auth.uid() = user_id);

-- Refresh PostgREST schema cache so PGRST205 clears immediately
notify pgrst, 'reload schema';
