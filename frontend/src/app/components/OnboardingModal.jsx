"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { supabase } from "../lib/supabase";
import { API_BASE } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useToast } from "./Toast";
import { Spinner } from "./Loaders";
import { prewarmIntelligence } from "../lib/prewarm";

/**
 * OnboardingModal
 * ---------------
 * One-screen wizard shown to brand-new users (no portfolio + no watchlist).
 * Gets them to "personalized dashboard" in under 60 seconds.
 *
 *  - Ticker autocomplete (uses /api/stocks/search)
 *  - One-tap quick-add suggestions (top NIFTY names)
 *  - On submit: bulk-insert into watchlist (no quantity/buy-price friction)
 *  - "Skip for now" → demo dashboard
 *  - Skip / completion both set localStorage flag so the modal doesn't reopen
 */

const STORAGE_KEY = "fincontext_onboarding_v1";

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

export default function OnboardingModal({ open, onClose, userName }) {
  const { user } = useAuth();
  const toast = useToast();
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState([]); // [{ticker, name}]
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
  };

  const handleSkip = useCallback(() => {
    try { localStorage.setItem(STORAGE_KEY, "skipped"); } catch {}
    onClose?.();
  }, [onClose]);

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

      try { localStorage.setItem(STORAGE_KEY, "completed"); } catch {}
      // Warm the news-feed cache for the new universe before the page reloads
      // so the dashboard paint after reload is sub-second.
      try {
        prewarmIntelligence({
          positions: [],
          watchlistTickers: selected.map((s) => s.ticker),
        });
      } catch { /* best-effort */ }
      toast.success(`Tracking ${selected.length} ${selected.length === 1 ? "stock" : "stocks"}`);
      onClose?.();
      // Soft-reload so all components pick up the new universe.
      setTimeout(() => window.location.reload(), 300);
    } catch (e) {
      toast.error(e?.message || "Could not save your watchlist.");
    } finally {
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
        background: "rgba(10,14,23,0.78)",
        backdropFilter: "blur(6px)",
        WebkitBackdropFilter: "blur(6px)",
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
      `}</style>
      <div
        style={{
          width: "min(560px, 100%)",
          maxHeight: "calc(100vh - 40px)",
          background: "var(--color-bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "16px",
          padding: "28px",
          boxShadow: "0 24px 60px rgba(0,0,0,0.5)",
          display: "flex",
          flexDirection: "column",
          gap: "18px",
          animation: "fc-rise 0.24s ease-out",
          overflow: "hidden",
        }}
      >
        {/* HEADER */}
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "10px" }}>
            <div
              style={{
                width: "40px",
                height: "40px",
                borderRadius: "10px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "20px",
                background:
                  "linear-gradient(135deg, var(--color-accent-primary), var(--color-accent-cyan))",
                color: "white",
                fontWeight: 800,
              }}
            >
              F
            </div>
            <div>
              <h2
                className="gradient-text"
                style={{
                  fontSize: "18px",
                  fontWeight: 800,
                  letterSpacing: "-0.01em",
                  lineHeight: 1.2,
                }}
              >
                Welcome{userName ? `, ${userName.split(" ")[0]}` : ""}!
              </h2>
              <p
                style={{
                  fontSize: "12px",
                  color: "var(--color-text-muted)",
                  marginTop: "3px",
                }}
              >
                Tell us what to track — we'll personalize your news feed.
              </p>
            </div>
          </div>
        </div>

        {/* SEARCH */}
        <div style={{ position: "relative" }}>
          <input
            ref={searchInputRef}
            type="text"
            placeholder="Search stocks — type RELIANCE, INFY, TATAPOWER…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            style={{
              width: "100%",
              padding: "11px 14px 11px 38px",
              borderRadius: "10px",
              border: "1px solid var(--border-subtle)",
              background: "var(--color-bg-secondary)",
              color: "var(--color-text-primary)",
              fontSize: "14px",
              outline: "none",
            }}
          />
          <span
            style={{
              position: "absolute",
              left: "12px",
              top: "50%",
              transform: "translateY(-50%)",
              fontSize: "14px",
              color: "var(--color-text-muted)",
            }}
          >
            🔍
          </span>
          {searching && (
            <div
              style={{
                position: "absolute",
                right: "12px",
                top: "50%",
                transform: "translateY(-50%)",
              }}
            >
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
                borderRadius: "10px",
                maxHeight: "260px",
                overflowY: "auto",
                zIndex: 10,
                boxShadow: "0 12px 28px rgba(0,0,0,0.4)",
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
                    onMouseEnter={(e) => {
                      if (!already) e.currentTarget.style.background = "rgba(99,102,241,0.08)";
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = "transparent";
                    }}
                  >
                    <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                      <span
                        style={{
                          fontWeight: 700,
                          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
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
                        fontSize: "12px",
                        fontWeight: 700,
                        color: already
                          ? "var(--color-accent-green)"
                          : "var(--color-accent-secondary)",
                      }}
                    >
                      {already ? "✓" : "+ Add"}
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
                fontSize: "10px",
                fontWeight: 800,
                textTransform: "uppercase",
                letterSpacing: "0.08em",
                color: "var(--color-text-muted)",
                marginBottom: "8px",
              }}
            >
              Quick add — popular NIFTY names
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
                      padding: "5px 10px",
                      borderRadius: "9999px",
                      border: already
                        ? "1px solid var(--color-accent-green)"
                        : "1px solid var(--border-subtle)",
                      background: already ? "rgba(16,185,129,0.10)" : "transparent",
                      color: already
                        ? "var(--color-accent-green)"
                        : "var(--color-text-secondary)",
                      fontSize: "11px",
                      fontWeight: 700,
                      cursor: already ? "default" : "pointer",
                      fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
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

        {/* SELECTED */}
        {selected.length > 0 && (
          <div
            style={{
              padding: "12px 14px",
              background: "var(--color-bg-secondary)",
              borderRadius: "10px",
              border: "1px solid var(--border-subtle)",
              maxHeight: "180px",
              overflowY: "auto",
            }}
          >
            <p
              style={{
                fontSize: "10px",
                fontWeight: 800,
                textTransform: "uppercase",
                letterSpacing: "0.08em",
                color: "var(--color-text-muted)",
                marginBottom: "8px",
              }}
            >
              Tracking ({selected.length})
            </p>
            <div style={{ display: "flex", gap: "5px", flexWrap: "wrap" }}>
              {selected.map((s) => (
                <span
                  key={s.ticker}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "5px",
                    padding: "3px 6px 3px 10px",
                    borderRadius: "6px",
                    background: "rgba(99,102,241,0.12)",
                    color: "var(--color-accent-secondary)",
                    border: "1px solid rgba(99,102,241,0.22)",
                    fontSize: "11px",
                    fontWeight: 700,
                    fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                  }}
                >
                  {s.ticker}
                  <button
                    type="button"
                    onClick={() => removeStock(s.ticker)}
                    aria-label={`Remove ${s.ticker}`}
                    style={{
                      background: "transparent",
                      border: "none",
                      color: "var(--color-text-muted)",
                      fontSize: "13px",
                      lineHeight: 1,
                      cursor: "pointer",
                      padding: 0,
                    }}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          </div>
        )}

        {/* FOOTER */}
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
              borderRadius: "8px",
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
              padding: "10px 22px",
              borderRadius: "10px",
              border: "none",
              background: selected.length === 0
                ? "var(--color-bg-secondary)"
                : "linear-gradient(135deg, var(--color-accent-primary), var(--color-accent-cyan))",
              color: selected.length === 0 ? "var(--color-text-muted)" : "white",
              fontSize: "13px",
              fontWeight: 700,
              cursor: selected.length === 0 || submitting ? "not-allowed" : "pointer",
              opacity: submitting ? 0.7 : 1,
              display: "flex",
              alignItems: "center",
              gap: "8px",
            }}
          >
            {submitting && <Spinner size="sm" />}
            {submitting
              ? "Saving…"
              : selected.length === 0
                ? "Add at least one stock"
                : `Track ${selected.length} ${selected.length === 1 ? "stock" : "stocks"} →`}
          </button>
        </div>
      </div>
    </div>
  );
}

/** Helper for callers: should the onboarding modal show on this load? */
export function shouldShowOnboarding({ hasPortfolio, hasWatchlist }) {
  if (typeof window === "undefined") return false;
  if (hasPortfolio || hasWatchlist) return false;
  try {
    return !localStorage.getItem(STORAGE_KEY);
  } catch {
    return true;
  }
}
