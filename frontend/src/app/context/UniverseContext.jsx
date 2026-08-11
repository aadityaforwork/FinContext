"use client";

/**
 * UniverseContext — one source of truth for "what the user holds and watches".
 * ---------------------------------------------------------------------------
 * Before this existed, every dashboard pane fetched the same data for itself:
 * PortfolioTodayStrip, MarketBriefStrip, NewsImpactFeed and UniverseRail each
 * ran their own `supabase.from("portfolio")` (+ most of them a watchlist read
 * too) — 7 round-trips for 2 tables' worth of data. Worse, each of those reads
 * was a *serial gate*: the pane could not start its backend call until its own
 * Supabase query came back, so the slowest link in every pane's waterfall was
 * duplicated work.
 *
 * Two panes then POSTed the byte-identical body to /api/portfolio/enrich
 * (PortfolioTodayStrip for the P&L strip, UniverseRail for the holdings list),
 * doubling the most frequently hit backend endpoint on the dashboard.
 *
 * This provider does both once:
 *   • one portfolio + watchlist read, shared by every consumer
 *   • one in-flight /api/portfolio/enrich promise, deduped by portfolio content
 *
 * Consumers get `{ positions, watchlistTickers, loading, ready, refresh,
 * getEnriched }`. `ready` distinguishes "loaded, and the user genuinely has
 * nothing" from "still loading" — panes use it to decide when to fall back to
 * demo data, which they previously inferred from a null check on their own
 * fetch.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";

import { API_BASE } from "../lib/api";
import { supabase } from "../lib/supabase";
import { useAuth } from "./AuthContext";

const UniverseContext = createContext(null);

/** Stable identity for a set of positions — used to dedupe the enrich call. */
function positionsKey(positions) {
  return (positions || [])
    .map((p) => `${p.ticker}:${p.quantity}:${p.buy_price}`)
    .sort()
    .join("|");
}

export function UniverseProvider({ children }) {
  const { user } = useAuth();
  const [positions, setPositions] = useState(null);
  const [watchlistTickers, setWatchlistTickers] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!user?.id) return;
    setLoading(true);
    try {
      const [{ data: pos }, { data: watch }] = await Promise.all([
        supabase
          .from("portfolio")
          .select("ticker, quantity, buy_price")
          .eq("user_id", user.id),
        supabase.from("watchlist").select("ticker").eq("user_id", user.id),
      ]);
      setPositions(pos || []);
      setWatchlistTickers((watch || []).map((r) => r.ticker));
    } catch {
      // Treat a failed read as "empty" rather than leaving panes spinning
      // forever — each one has its own demo/degraded state for this.
      setPositions([]);
      setWatchlistTickers([]);
    } finally {
      setLoading(false);
    }
  }, [user?.id]);

  useEffect(() => {
    load();
  }, [load]);

  // Shared /api/portfolio/enrich. Keyed by portfolio content so a mutation
  // invalidates it, but two panes mounting in the same frame share one request.
  const enrichRef = useRef({ key: null, promise: null });

  const getEnriched = useCallback(() => {
    if (!positions || positions.length === 0) return Promise.resolve(null);
    const key = positionsKey(positions);
    if (enrichRef.current.key === key && enrichRef.current.promise) {
      return enrichRef.current.promise;
    }
    const promise = fetch(`${API_BASE}/api/portfolio/enrich`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ positions }),
    })
      .then((res) => (res.ok ? res.json() : null))
      .catch(() => null);
    enrichRef.current = { key, promise };
    return promise;
  }, [positions]);

  const refresh = useCallback(() => {
    enrichRef.current = { key: null, promise: null };
    return load();
  }, [load]);

  const value = {
    positions,
    watchlistTickers,
    loading,
    // `ready` means the Supabase reads have resolved at least once.
    ready: positions !== null && watchlistTickers !== null,
    refresh,
    getEnriched,
  };

  return (
    <UniverseContext.Provider value={value}>{children}</UniverseContext.Provider>
  );
}

/**
 * Panes outside the provider (or rendered before it mounts) get a null-shaped
 * fallback rather than a throw, so a stray consumer can't blank the dashboard.
 */
export function useUniverse() {
  return (
    useContext(UniverseContext) || {
      positions: null,
      watchlistTickers: null,
      loading: true,
      ready: false,
      refresh: () => Promise.resolve(),
      getEnriched: () => Promise.resolve(null),
    }
  );
}
