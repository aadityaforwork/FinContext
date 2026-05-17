"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { supabase } from "../lib/supabase";
import { API_BASE } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useToast } from "./Toast";
import { Spinner } from "./Loaders";
import { prewarmIntelligence } from "../lib/prewarm";

/**
 * OnboardingModal — Smart Wizard (Act 1 of the "First Five Minutes")
 * -------------------------------------------------------------------
 * Gets a brand-new user to a personalized dashboard in <60s. Key upgrade
 * over the old wizard: as the user adds tickers, the panel below the
 * search shows LIVE DATA for each pick (price, day change, sector). The
 * user sees the product working before clicking Continue — the wizard
 * itself is the first "wow" surface.
 *
 * Visual style matches the editorial-terminal aesthetic used across the
 * rest of the app: flat monogram (no gradient), hairline borders, solid
 * accent button, mono labels. No emojis.
 *
 * After completion this modal triggers the FirstInsightCard interstitial
 * (Act 2) via `onComplete(tickers)` instead of the old full page reload.
 */

// Storage keys are scoped per-user — two different accounts on the same
// browser must not share onboarding state, or the second user's first-run
// will be silently suppressed because the first user already completed it.
const STORAGE_KEY_BASE = "fincontext_onboarding_v2";
const keyFor = (userId) => `${STORAGE_KEY_BASE}_${userId || "anon"}`;

// SessionStorage keys used to carry the post-wizard state across the
// dashboard reload — they're consumed (and removed) on the next page load.
const SS_PENDING_INSIGHT = "fincontext_pending_insight_tickers";
const SS_PENDING_TOUR    = "fincontext_pending_tour";

// Pre-curated quick-add chips — covers ~70% of typical Indian retail interest.
const QUICK_ADD = [
  { ticker: "RELIANCE",   name: "Reliance Industries" },
  { ticker: "TCS",        name: "Tata Consultancy" },
  { ticker: "HDFCBANK",   name: "HDFC Bank" },
  { ticker: "INFY",       name: "Infosys" },
  { ticker: "ICICIBANK",  name: "ICICI Bank" },
  { ticker: "ITC",        name: "ITC" },
  { ticker: "BHARTIARTL", name: "Bharti Airtel" },
  { ticker: "LT",         name: "Larsen & Toubro" },
];

export default function OnboardingModal({ open, onClose, onComplete, userName }) {
  const { user } = useAuth();
  const toast = useToast();
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState([]); // [{ticker, name}]
  // Live data per ticker: { ticker: {current_price, change_percent, sector, status: "loading"|"ok"|"err"} }
  const [livePrices, setLivePrices] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const searchInputRef = useRef(null);

  // Auto-focus search when modal opens.
  useEffect(() => {
    if (open && searchInputRef.current) {
      setTimeout(() => searchInputRef.current?.focus(), 250);
    }
  }, [open]);

  // Lock scroll under modal.
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, [open]);

  // Debounce search input.
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(query), 250);
    return () => clearTimeout(t);
  }, [query]);

  // Search NSE catalog.
  useEffect(() => {
    if (!open) return;
    if (debouncedQuery.length < 2) { setResults([]); return; }
    setSearching(true);
    const ctrl = new AbortController();
    fetch(`${API_BASE}/api/stocks/search?q=${encodeURIComponent(debouncedQuery)}&limit=8`, {
      signal: ctrl.signal,
    })
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => { setResults(data || []); setSearching(false); })
      .catch((err) => { if (err.name !== "AbortError") setSearching(false); });
    return () => ctrl.abort();
  }, [open, debouncedQuery]);

  // LIVE PREVIEW — fetch /api/watchlist/prices for any selected tickers we
  // don't have yet. Debounced 350ms so rapid additions don't fire 4 requests
  // in 2 seconds. Failures fall back to a muted "—" — never blocks Continue.
  useEffect(() => {
    if (!open || selected.length === 0) return;
    const missing = selected
      .map((s) => s.ticker)
      .filter((t) => !livePrices[t] || livePrices[t].status === "loading");
    if (missing.length === 0) return;

    // Mark as loading so the UI shows a spinner immediately.
    setLivePrices((prev) => {
      const next = { ...prev };
      for (const t of missing) next[t] = { ...(next[t] || {}), status: "loading" };
      return next;
    });

    const ctrl = new AbortController();
    const id = setTimeout(() => {
      fetch(`${API_BASE}/api/watchlist/prices`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tickers: missing }),
        signal: ctrl.signal,
      })
        .then((r) => (r.ok ? r.json() : {}))
        .then((data) => {
          setLivePrices((prev) => {
            const next = { ...prev };
            for (const t of missing) {
              const row = data?.[t];
              if (row) {
                next[t] = {
                  current_price: row.current_price,
                  change_percent: row.change_percent,
                  sector: row.sector,
                  name: row.name,
                  status: "ok",
                };
              } else {
                next[t] = { status: "err" };
              }
            }
            return next;
          });
        })
        .catch((err) => {
          if (err.name === "AbortError") return;
          setLivePrices((prev) => {
            const next = { ...prev };
            for (const t of missing) next[t] = { status: "err" };
            return next;
          });
        });
    }, 350);
    return () => { clearTimeout(id); ctrl.abort(); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, selected]);

  const isSelected = (ticker) => selected.some((s) => s.ticker === ticker);

  const addStock = (stock) => {
    if (isSelected(stock.ticker)) return;
    if (selected.length >= 15) {
      toast.info("You can add up to 15 stocks in the wizard. More can be added later.");
      return;
    }
    setSelected((prev) => [...prev, { ticker: stock.ticker, name: stock.name }]);
    setQuery("");
    setResults([]);
  };

  const removeStock = (ticker) => {
    setSelected((prev) => prev.filter((s) => s.ticker !== ticker));
    setLivePrices((prev) => {
      const next = { ...prev };
      delete next[ticker];
      return next;
    });
  };

  const handleSkip = useCallback(() => {
    try { localStorage.setItem(keyFor(user?.id), "skipped"); } catch {}
    onClose?.();
  }, [onClose, user?.id]);

  const handleContinue = async () => {
    if (!user?.id || selected.length === 0) return;
    setSubmitting(true);
    try {
      // Bulk-add to watchlist. Existing rows silently kept via upsert with
      // ignoreDuplicates so re-running is safe.
      const rows = selected.map((s) => ({ ticker: s.ticker, user_id: user.id }));
      const { error } = await supabase
        .from("watchlist")
        .upsert(rows, { onConflict: "ticker,user_id", ignoreDuplicates: true });

      if (error) throw error;

      try { localStorage.setItem(keyFor(user?.id), "completed"); } catch {}
      // Warm the news-feed cache for the new universe before the page reloads
      // so the dashboard paint after reload is sub-second.
      try {
        prewarmIntelligence({
          positions: [],
          watchlistTickers: selected.map((s) => s.ticker),
        });
      } catch { /* best-effort */ }

      // KEY FLOW FIX (was choppy): we used to call onComplete → open the
      // FirstInsightCard over an empty dashboard → user dismisses → reload
      // → dashboard re-renders empty for a moment → tour fires. That's the
      // chop the user reported.
      //
      // New flow: stash the post-wizard state in sessionStorage and reload
      // RIGHT NOW. The next page load picks up the flag, opens the
      // FirstInsightCard over a freshly-loaded dashboard, then on dismiss
      // fires the tour. No mid-flow reload, no flicker.
      const pickedTickers = selected.map((s) => s.ticker);
      try {
        sessionStorage.setItem(SS_PENDING_INSIGHT, JSON.stringify(pickedTickers));
        sessionStorage.setItem(SS_PENDING_TOUR, "1");
      } catch { /* best-effort */ }
      // The onComplete prop is still supported (e.g. for tests/storybook).
      if (typeof onComplete === "function") onComplete(pickedTickers);
      // Hard reload — destroys this React tree, the next mount reads the
      // sessionStorage flag and continues the flow.
      window.location.reload();
    } catch (e) {
      toast.error(e?.message || "Could not save your watchlist.");
      setSubmitting(false);
    }
  };

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.72)",
        backdropFilter: "blur(8px)",
        WebkitBackdropFilter: "blur(8px)",
        zIndex: 1000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "20px",
        animation: "fc-fade 0.18s ease-out",
      }}
    >
      <style>{`
        @keyframes fc-fade { from { opacity: 0 } to { opacity: 1 } }
        @keyframes fc-rise { from { transform: translateY(12px); opacity: 0 } to { transform: translateY(0); opacity: 1 } }
        @keyframes fc-flash { 0% { background: rgba(99,102,241,0.18) } 100% { background: var(--color-bg-card) } }
      `}</style>
      <div
        style={{
          width: "min(580px, 100%)",
          maxHeight: "calc(100vh - 40px)",
          background: "var(--color-bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-card, 12px)",
          padding: "28px",
          display: "flex",
          flexDirection: "column",
          gap: "20px",
          animation: "fc-rise 0.24s ease-out",
          overflow: "hidden",
        }}
      >
        {/* HEADER — flat monogram matches Sidebar + AuthCard. Editorial type. */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "12px",
            paddingBottom: "18px",
            borderBottom: "1px solid var(--border-subtle)",
          }}
        >
          <div
            style={{
              width: "32px",
              height: "32px",
              borderRadius: "7px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--color-text-primary)",
              fontWeight: 700,
              fontSize: "15px",
              flexShrink: 0,
              background: "var(--color-bg-card-hover)",
              border: "1px solid var(--border-strong)",
              letterSpacing: "-0.03em",
            }}
          >
            F
          </div>
          <div style={{ lineHeight: 1.3 }}>
            <h2
              style={{
                fontSize: "16px",
                fontWeight: 700,
                color: "var(--color-text-primary)",
                letterSpacing: "-0.01em",
              }}
            >
              Welcome{userName ? `, ${userName.split(" ")[0]}` : ""}
            </h2>
            <p style={{ fontSize: "12.5px", color: "var(--color-text-muted)", marginTop: "3px" }}>
              Pick a few stocks — we&apos;ll pull signals as you go.
            </p>
          </div>
        </div>

        {/* SEARCH */}
        <div style={{ position: "relative" }}>
          <input
            ref={searchInputRef}
            type="text"
            placeholder="Search RELIANCE, INFY, TATAPOWER…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            style={{
              width: "100%",
              padding: "11px 14px",
              borderRadius: "var(--radius-control, 8px)",
              border: "1px solid var(--border-subtle)",
              background: "var(--color-bg-secondary)",
              color: "var(--color-text-primary)",
              fontSize: "13.5px",
              outline: "none",
            }}
          />
          {searching && (
            <div style={{ position: "absolute", right: "12px", top: "50%", transform: "translateY(-50%)" }}>
              <Spinner size="sm" />
            </div>
          )}

          {/* Search results dropdown */}
          {results.length > 0 && (
            <div
              style={{
                position: "absolute",
                top: "calc(100% + 4px)",
                left: 0,
                right: 0,
                background: "var(--color-bg-card)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-control, 8px)",
                maxHeight: "260px",
                overflowY: "auto",
                zIndex: 10,
                boxShadow: "var(--shadow-pop)",
              }}
            >
              {results.map((s) => {
                const already = isSelected(s.ticker);
                return (
                  <button
                    key={s.ticker}
                    type="button"
                    onClick={() => !already && addStock(s)}
                    disabled={already}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      width: "100%",
                      padding: "9px 14px",
                      border: "none",
                      background: "transparent",
                      color: "var(--color-text-primary)",
                      fontSize: "13px",
                      cursor: already ? "default" : "pointer",
                      borderBottom: "1px solid var(--border-subtle)",
                      textAlign: "left",
                      opacity: already ? 0.5 : 1,
                    }}
                    onMouseEnter={(e) => { if (!already) e.currentTarget.style.background = "var(--color-bg-card-hover)"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
                  >
                    <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                      <span
                        style={{
                          fontWeight: 700,
                          fontFamily: "var(--font-mono)",
                          fontSize: "12.5px",
                        }}
                      >
                        {s.ticker}
                      </span>
                      <span style={{ fontSize: "11px", color: "var(--color-text-muted)" }}>
                        {s.name} · {s.sector}
                      </span>
                    </div>
                    <span
                      style={{
                        fontSize: "11px",
                        fontWeight: 700,
                        letterSpacing: "0.06em",
                        color: already
                          ? "var(--color-accent-green)"
                          : "var(--color-accent-secondary)",
                      }}
                    >
                      {already ? "ADDED" : "+ ADD"}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* QUICK ADD */}
        {selected.length < 8 && (
          <div>
            <p
              style={{
                fontSize: "9.5px",
                fontWeight: 700,
                textTransform: "uppercase",
                letterSpacing: "0.16em",
                color: "var(--color-text-muted)",
                marginBottom: "9px",
                fontFamily: "var(--font-mono)",
              }}
            >
              Quick add · popular NIFTY
            </p>
            <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
              {QUICK_ADD.map((s) => {
                const already = isSelected(s.ticker);
                return (
                  <button
                    key={s.ticker}
                    type="button"
                    onClick={() => addStock(s)}
                    disabled={already}
                    style={{
                      padding: "5px 11px",
                      borderRadius: "var(--radius-pill, 6px)",
                      border: already
                        ? "1px solid var(--color-accent-green)"
                        : "1px solid var(--border-subtle)",
                      background: already ? "rgba(46,189,107,0.08)" : "transparent",
                      color: already
                        ? "var(--color-accent-green)"
                        : "var(--color-text-secondary)",
                      fontSize: "11px",
                      fontWeight: 700,
                      letterSpacing: "0.04em",
                      cursor: already ? "default" : "pointer",
                      fontFamily: "var(--font-mono)",
                    }}
                  >
                    {already ? "✓ " : "+ "}
                    {s.ticker}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* LIVE PREVIEW — the wizard's "wow" surface. Each picked ticker
            shows live price + change as soon as it's been added. */}
        {selected.length > 0 && (
          <div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: "10px",
              }}
            >
              <p
                style={{
                  fontSize: "9.5px",
                  fontWeight: 700,
                  textTransform: "uppercase",
                  letterSpacing: "0.16em",
                  color: "var(--color-text-muted)",
                  fontFamily: "var(--font-mono)",
                }}
              >
                Your picks ({selected.length})
              </p>
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "5px",
                  fontSize: "9.5px",
                  fontWeight: 700,
                  letterSpacing: "0.14em",
                  color: "var(--color-accent-primary)",
                  fontFamily: "var(--font-mono)",
                }}
              >
                <span
                  className="oc-pulse-dot"
                  style={{
                    width: "5px",
                    height: "5px",
                    borderRadius: "50%",
                    background: "var(--color-accent-primary)",
                  }}
                />
                LIVE
              </span>
            </div>
            <div
              style={{
                background: "var(--color-bg-secondary)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-control, 8px)",
                maxHeight: "230px",
                overflowY: "auto",
              }}
            >
              {selected.map((s, i) => (
                <LivePreviewRow
                  key={s.ticker}
                  ticker={s.ticker}
                  fallbackName={s.name}
                  data={livePrices[s.ticker]}
                  onRemove={() => removeStock(s.ticker)}
                  isLast={i === selected.length - 1}
                />
              ))}
            </div>
          </div>
        )}

        {/* FOOTER — editorial styling: solid accent button, no gradient. */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "12px",
            paddingTop: "8px",
            borderTop: "1px solid var(--border-subtle)",
          }}
        >
          <button
            type="button"
            onClick={handleSkip}
            style={{
              padding: "9px 14px",
              borderRadius: "var(--radius-control, 8px)",
              border: "none",
              background: "transparent",
              color: "var(--color-text-muted)",
              fontSize: "12px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Skip for now
          </button>
          <button
            type="button"
            onClick={handleContinue}
            disabled={selected.length === 0 || submitting}
            style={{
              padding: "11px 22px",
              borderRadius: "var(--radius-control, 8px)",
              border: selected.length === 0
                ? "1px solid var(--border-subtle)"
                : "1px solid var(--color-accent-primary)",
              background: selected.length === 0
                ? "var(--color-bg-card-hover)"
                : "var(--color-accent-primary)",
              color: selected.length === 0 ? "var(--color-text-muted)" : "#fff",
              fontSize: "13px",
              fontWeight: 700,
              letterSpacing: "0.02em",
              cursor: selected.length === 0 || submitting ? "not-allowed" : "pointer",
              opacity: submitting ? 0.7 : 1,
              display: "flex",
              alignItems: "center",
              gap: "8px",
              transition: "filter 0.15s",
            }}
            onMouseEnter={(e) => { if (selected.length > 0 && !submitting) e.currentTarget.style.filter = "brightness(1.12)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.filter = "none"; }}
          >
            {submitting && <Spinner size="sm" />}
            {submitting
              ? "Saving…"
              : selected.length === 0
                ? "Add at least one stock"
                : `Track ${selected.length} ${selected.length === 1 ? "stock" : "stocks"} →`}
          </button>
        </div>

        <style jsx>{`
          @keyframes oc-pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50%      { opacity: 0.45; transform: scale(1.4); }
          }
          :global(.oc-pulse-dot) { animation: oc-pulse 1.6s ease-in-out infinite; }
        `}</style>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// LivePreviewRow — one row in the wizard's live preview list. Shows live
// price + day change once the /api/watchlist/prices fetch resolves; spinner
// while loading; muted "—" if the fetch failed.
//
// Animates a brief indigo flash on first data arrival ("fc-flash" keyframe
// defined inside the modal) so the user perceives the value LANDING.
// ---------------------------------------------------------------------------
function LivePreviewRow({ ticker, fallbackName, data, onRemove, isLast }) {
  const status = data?.status || "loading";
  const price = data?.current_price;
  const chg = data?.change_percent;
  const sector = data?.sector;
  const name = data?.name || fallbackName || ticker;
  const isPos = typeof chg === "number" && chg >= 0;
  const chgColor =
    chg == null
      ? "var(--color-text-muted)"
      : isPos
      ? "var(--color-accent-green)"
      : "var(--color-accent-red)";

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr auto auto auto",
        alignItems: "center",
        gap: "12px",
        padding: "10px 14px",
        borderBottom: isLast ? "none" : "1px solid var(--border-subtle)",
        animation: status === "ok" ? "fc-flash 0.6s ease-out" : "none",
      }}
    >
      <div style={{ minWidth: 0 }}>
        <div
          style={{
            fontSize: "12.5px",
            fontWeight: 700,
            color: "var(--color-text-primary)",
            fontFamily: "var(--font-mono)",
          }}
        >
          {ticker}
        </div>
        <div
          style={{
            fontSize: "11px",
            color: "var(--color-text-muted)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {name}
          {sector ? ` · ${sector}` : ""}
        </div>
      </div>

      {/* Live price column */}
      <div
        style={{
          fontSize: "12.5px",
          fontWeight: 700,
          fontVariantNumeric: "tabular-nums",
          color: price != null ? "var(--color-text-primary)" : "var(--color-text-muted)",
          textAlign: "right",
          minWidth: "78px",
        }}
      >
        {status === "loading"
          ? <span style={{ opacity: 0.4 }}>fetching…</span>
          : price != null
            ? `₹${price.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`
            : "—"}
      </div>

      {/* Day change column */}
      <div
        style={{
          fontSize: "11.5px",
          fontWeight: 700,
          fontVariantNumeric: "tabular-nums",
          color: chgColor,
          textAlign: "right",
          minWidth: "56px",
        }}
      >
        {chg != null ? `${isPos ? "+" : ""}${chg.toFixed(2)}%` : ""}
      </div>

      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove ${ticker}`}
        style={{
          background: "transparent",
          border: "none",
          color: "var(--color-text-muted)",
          fontSize: "16px",
          lineHeight: 1,
          cursor: "pointer",
          padding: "2px 6px",
          borderRadius: "4px",
        }}
        onMouseEnter={(e) => { e.currentTarget.style.color = "var(--color-accent-red)"; }}
        onMouseLeave={(e) => { e.currentTarget.style.color = "var(--color-text-muted)"; }}
      >
        ×
      </button>
    </div>
  );
}

/** Helper for callers: should the onboarding modal show on this load?
 *
 * Storage is scoped by user.id so two accounts on the same browser don't
 * step on each other — the old `fincontext_onboarding_v1` flag was a
 * single browser-wide string, which silently suppressed onboarding for
 * any second user on the same machine. That's why "nothing happened on
 * signup" — the flag was already set from a prior session.
 */
export function shouldShowOnboarding({ hasPortfolio, hasWatchlist, userId }) {
  if (typeof window === "undefined") return false;
  if (hasPortfolio || hasWatchlist) return false;
  try {
    return !localStorage.getItem(keyFor(userId));
  } catch {
    return true;
  }
}

/** Used by Settings → "Replay onboarding" to wipe all 3 flags for this user. */
export function resetOnboarding(userId) {
  if (typeof window === "undefined") return;
  try { localStorage.removeItem(keyFor(userId)); } catch {}
  try { localStorage.removeItem(`fincontext_first_insight_seen_v2_${userId || "anon"}`); } catch {}
  try { localStorage.removeItem(`fincontext_tour_seen_v2_${userId || "anon"}`); } catch {}
  try { sessionStorage.removeItem(SS_PENDING_INSIGHT); } catch {}
  try { sessionStorage.removeItem(SS_PENDING_TOUR); } catch {}
}

/** Read + consume the post-wizard sessionStorage. Returns the ticker
 * list the wizard just inserted, or null. */
export function consumePendingFirstInsight() {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(SS_PENDING_INSIGHT);
    if (!raw) return null;
    sessionStorage.removeItem(SS_PENDING_INSIGHT);
    return JSON.parse(raw);
  } catch { return null; }
}

/** Read + consume the post-insight tour flag. Returns true if the tour
 * should fire after the FirstInsightCard dismisses. */
export function consumePendingTour() {
  if (typeof window === "undefined") return false;
  try {
    const v = sessionStorage.getItem(SS_PENDING_TOUR);
    if (v) {
      sessionStorage.removeItem(SS_PENDING_TOUR);
      return true;
    }
  } catch {}
  return false;
}
