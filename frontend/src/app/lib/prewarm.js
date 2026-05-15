"use client";

import { API_BASE } from "./api";

/**
 * Background prewarm — fire the heavy intelligence endpoints right after a
 * portfolio mutation so the backend cache is hot by the time the user lands
 * on the dashboard. Eliminates the new-user cold-load wait.
 *
 * Pattern: fire-and-forget. Both calls run in async IIFEs that consume the
 * full response (drain JSON / SSE) so the FastAPI handlers actually finish
 * and write to `response_cache` — but neither blocks the caller, throws, or
 * surfaces errors. Worst case: the prewarm fails and the user pays the same
 * cold-load they'd have paid anyway.
 */
export function prewarmIntelligence({ positions = [], watchlistTickers = [] } = {}) {
  const positionsClean = (positions || [])
    .filter((p) => p && p.ticker)
    .map((p) => ({
      ticker: String(p.ticker).toUpperCase(),
      quantity: Number(p.quantity) || 0,
      buy_price: Number(p.buy_price) || 0,
    }));
  const watchlistClean = (watchlistTickers || [])
    .filter(Boolean)
    .map((t) => String(t).toUpperCase());

  // News feed — runs even with empty positions (uses watchlist + market headlines).
  (async () => {
    try {
      const res = await fetch(`${API_BASE}/api/intelligence/news-feed`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          positions: positionsClean,
          watchlist_tickers: watchlistClean,
          force_refresh: false,
        }),
      });
      // Drain body so the server-side handler completes and writes the cache.
      await res.text();
    } catch {
      // Silently swallow — prewarm is best-effort.
    }
  })();

  // Movers (Context Engine) — only meaningful with at least one holding.
  if (positionsClean.length > 0) {
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/intelligence/movers`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            positions: positionsClean,
            force_refresh: false,
          }),
        });
        // /movers is an SSE stream — we must drain to [DONE] so the inner
        // generator yields its final result + the wrapper writes the cache.
        if (res.body) {
          const reader = res.body.getReader();
          // eslint-disable-next-line no-constant-condition
          while (true) {
            const { done } = await reader.read();
            if (done) break;
          }
        }
      } catch {
        // Silently swallow.
      }
    })();
  }
}
