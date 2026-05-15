"use client";

import { useState, useEffect, useRef, useCallback } from "react";

/**
 * useCache — instant paint via localStorage + background refresh.
 * ----------------------------------------------------------------
 * The dashboard endpoints (news-feed, context-engine, etc.) take 5–60s on a
 * cold Render worker. This hook makes the *second visit onwards* feel instant:
 *
 *   1. On mount — synchronously read localStorage. If a cached value exists for
 *      this `key + version` and it's not older than `maxAgeMs`, render it
 *      immediately with `stale=true` and `loading=false`.
 *   2. Always fire `fetchFn` — silent if we already painted from cache, with
 *      `loading=true` if not. On success, replace `data` and persist to
 *      localStorage. On failure, keep the stale paint and surface `error`.
 *
 * `version` is the cache-bust token. Pass a hash of the request inputs (e.g.
 * sorted portfolio tickers + watchlist) — when it changes, the cached value is
 * treated as a miss so a Bank-of-Baroda news entry doesn't bleed over after
 * the user adds RELIANCE.
 *
 * Returns:
 *   { data, loading, stale, error, refreshedAt, refresh }
 *
 *   data         — the cached or fresh response (null until first fetch)
 *   loading      — true only on the very first paint (no cache hit)
 *   stale        — true while showing a cached value during a background refresh
 *   error        — last fetch error, if any
 *   refreshedAt  — ms timestamp of the last successful network refresh
 *   refresh()    — manually re-fire the fetch (silent: keeps current data on screen)
 *
 * Storage layout: `fc:cache:<key>|v:<version>` → JSON `{ data, ts }`.
 * Old versions for the same key are NOT auto-evicted — they just go cold; a
 * stale-cleanup pass on app start could be added later.
 */
export function useCache(key, fetchFn, opts = {}) {
  const { version = "", maxAgeMs = 60 * 60 * 1000, enabled = true } = opts;
  const fullKey = `fc:cache:${key}|v:${version}`;

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [stale, setStale] = useState(false);
  const [error, setError] = useState(null);
  const [refreshedAt, setRefreshedAt] = useState(null);

  // Latest fetchFn — refs let `refresh()` stay stable across re-renders.
  const fetchRef = useRef(fetchFn);
  fetchRef.current = fetchFn;

  const refresh = useCallback(
    async (silent = false, ...args) => {
      if (!silent) setLoading(true);
      setError(null);
      try {
        // Forward any extra args to fetchFn — lets callers pass a `force`
        // flag to bypass server-side SWR (e.g. user-clicked refresh).
        const fresh = await fetchRef.current(...args);
        setData(fresh);
        setStale(false);
        setRefreshedAt(Date.now());
        try {
          localStorage.setItem(
            fullKey,
            JSON.stringify({ data: fresh, ts: Date.now() })
          );
        } catch {
          // Quota exceeded / private mode — non-fatal, just skip persistence.
        }
        return fresh;
      } catch (e) {
        setError(e?.message || String(e));
        throw e;
      } finally {
        setLoading(false);
      }
    },
    [fullKey]
  );

  useEffect(() => {
    if (!enabled) return undefined;
    let cancelled = false;
    let cachedHit = false;

    // Synchronous localStorage read — paints in the same frame.
    try {
      const raw = typeof window !== "undefined" ? localStorage.getItem(fullKey) : null;
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed?.data && Date.now() - (parsed.ts || 0) < maxAgeMs) {
          if (!cancelled) {
            setData(parsed.data);
            setStale(true);
            setLoading(false);
            cachedHit = true;
          }
        }
      }
    } catch {
      // Bad JSON — ignore and refetch.
    }

    refresh(cachedHit).catch(() => {
      // Errors already captured into state by `refresh`.
    });

    return () => {
      cancelled = true;
    };
    // We deliberately exclude `refresh` from deps — it's already stable via
    // its own useCallback on `fullKey`, and re-running this effect should
    // happen only when `fullKey` or `enabled` changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fullKey, enabled]);

  return { data, loading, stale, error, refreshedAt, refresh };
}

/**
 * Stable hash for cache versioning. Sorts + lowercases each part so two
 * portfolios with the same tickers in different orders share a key.
 */
export function makeCacheVersion(...parts) {
  const norm = parts.map((p) => {
    if (Array.isArray(p)) {
      return [...p]
        .map((x) => (typeof x === "string" ? x.toLowerCase() : String(x)))
        .sort()
        .join(",");
    }
    return p == null ? "" : String(p).toLowerCase();
  });
  return norm.join("|");
}
