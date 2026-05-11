"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { supabase } from "../lib/supabase";
import { API_BASE } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Spinner } from "./Loaders";

/**
 * MarketBriefStrip
 * ----------------
 * Single-row hero strip: shows just the one-line `headline` from the market
 * summary endpoint. Clicking it opens a right-side drawer with the full
 * 60-line narrative. The full content is heavy; keeping it off the main
 * canvas is what makes the dashboard feel premium.
 */

const SECTION_META = {
  overnight:      { icon: "🌙", title: "Overnight" },
  india_open:     { icon: "🇮🇳", title: "India open" },
  your_portfolio: { icon: "📊", title: "Your portfolio" },
  sector_pulse:   { icon: "🏭", title: "Sector pulse" },
  watch_today:    { icon: "👀", title: "Watch today" },
  tomorrow_setup: { icon: "🔮", title: "Tomorrow setup" },
};

const STANCE_COLOR = {
  tailwind: "var(--color-accent-green)",
  headwind: "var(--color-accent-red)",
  mixed:    "var(--color-accent-amber)",
  neutral:  "var(--color-text-muted)",
};

export default function MarketBriefStrip({ onNavigate }) {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(false);
  const drawerRef = useRef(null);

  const fetchSummary = useCallback(async (force = false) => {
    if (!user?.id) return;
    if (force) setRefreshing(true); else setLoading(true);
    try {
      const [{ data: positions }, { data: watchRows }] = await Promise.all([
        supabase.from("portfolio").select("ticker, quantity, buy_price").eq("user_id", user.id),
        supabase.from("watchlist").select("ticker").eq("user_id", user.id),
      ]);
      const res = await fetch(`${API_BASE}/api/intelligence/market-summary`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          positions: positions || [],
          watchlist_tickers: (watchRows || []).map((r) => r.ticker),
          force_refresh: force,
        }),
      });
      if (res.ok) setData(await res.json());
    } catch { /* drawer shows error state */ }
    finally { setLoading(false); setRefreshing(false); }
  }, [user?.id]);

  useEffect(() => { fetchSummary(false); }, [fetchSummary]);

  // Close drawer on Escape
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const headline = data?.headline || (loading ? "Drafting today's market view…" : "Today's market summary");

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        disabled={loading && !data}
        className="dash-strip dash-brief-strip"
        style={{
          width: "100%",
          padding: "12px 20px",
          borderRadius: "12px",
          background: "var(--color-bg-card)",
          border: "1px solid var(--border-subtle)",
          display: "flex",
          alignItems: "center",
          gap: "14px",
          textAlign: "left",
          cursor: loading && !data ? "wait" : "pointer",
          transition: "border-color 0.15s, background 0.15s",
        }}
        onMouseEnter={(e) => {
          if (!loading || data) {
            e.currentTarget.style.borderColor = "rgba(99,102,241,0.30)";
            e.currentTarget.style.background = "rgba(99,102,241,0.04)";
          }
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.borderColor = "var(--border-subtle)";
          e.currentTarget.style.background = "var(--color-bg-card)";
        }}
      >
        <span
          className="dbs-label"
          style={{
            fontSize: "9px",
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: "0.10em",
            color: "var(--color-text-muted)",
            flexShrink: 0,
          }}
        >
          Today's brief
        </span>
        <span
          className="dbs-sep"
          style={{
            width: "1px",
            height: "14px",
            background: "var(--border-subtle)",
            flexShrink: 0,
          }}
        />
        {loading && !data ? (
          <span style={{ display: "flex", alignItems: "center", gap: "8px", flex: 1 }}>
            <Spinner size="sm" />
            <span style={{ fontSize: "12px", color: "var(--color-text-muted)" }}>{headline}</span>
          </span>
        ) : (
          <span
            className="dbs-headline"
            style={{
              fontSize: "13px",
              fontWeight: 500,
              color: "var(--color-text-secondary)",
              flex: 1,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {headline}
          </span>
        )}
        <span
          className="dbs-cta"
          style={{
            fontSize: "11px",
            fontWeight: 700,
            color: "var(--color-accent-secondary)",
            letterSpacing: "0.02em",
            flexShrink: 0,
          }}
        >
          Read full →
        </span>
      </button>

      {/* DRAWER */}
      {open && (
        <div
          role="dialog"
          aria-modal="true"
          onClick={() => setOpen(false)}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(10,14,23,0.65)",
            backdropFilter: "blur(4px)",
            WebkitBackdropFilter: "blur(4px)",
            zIndex: 1000,
            display: "flex",
            justifyContent: "flex-end",
            animation: "fade-in 0.18s ease-out",
          }}
        >
          <style>{`@keyframes fade-in { from { opacity: 0 } to { opacity: 1 } }
                   @keyframes slide-in-right { from { transform: translateX(40px); opacity: 0 } to { transform: translateX(0); opacity: 1 } }`}</style>
          <div
            ref={drawerRef}
            onClick={(e) => e.stopPropagation()}
            style={{
              width: "min(560px, 92vw)",
              height: "100vh",
              background: "var(--color-bg-primary)",
              borderLeft: "1px solid var(--border-subtle)",
              padding: "20px 24px",
              overflowY: "auto",
              boxShadow: "-12px 0 40px rgba(0,0,0,0.4)",
              animation: "slide-in-right 0.22s ease-out",
            }}
          >
            {/* Drawer header */}
            <div
              style={{
                display: "flex",
                alignItems: "flex-start",
                justifyContent: "space-between",
                gap: "12px",
                paddingBottom: "16px",
                marginBottom: "16px",
                borderBottom: "1px solid var(--border-subtle)",
              }}
            >
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px" }}>
                  <span style={{ fontSize: "16px" }}>📖</span>
                  <h2
                    className="gradient-text"
                    style={{ fontSize: "16px", fontWeight: 800, letterSpacing: "-0.01em" }}
                  >
                    Today's market — for you
                  </h2>
                </div>
                {data?.headline && (
                  <p style={{ fontSize: "13px", color: "var(--color-text-secondary)", lineHeight: 1.4 }}>
                    {data.headline}
                  </p>
                )}
              </div>
              <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
                <button
                  type="button"
                  onClick={() => fetchSummary(true)}
                  disabled={refreshing}
                  aria-label="Refresh"
                  style={{
                    padding: "6px 10px",
                    borderRadius: "6px",
                    border: "1px solid var(--border-subtle)",
                    background: "var(--color-bg-card)",
                    color: "var(--color-text-muted)",
                    fontSize: "10px",
                    fontWeight: 700,
                    cursor: refreshing ? "wait" : "pointer",
                    opacity: refreshing ? 0.6 : 1,
                  }}
                >
                  {refreshing ? <Spinner size="sm" /> : "↻"}
                </button>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  aria-label="Close"
                  style={{
                    width: "28px",
                    height: "28px",
                    borderRadius: "8px",
                    border: "1px solid var(--border-subtle)",
                    background: "var(--color-bg-card)",
                    color: "var(--color-text-secondary)",
                    cursor: "pointer",
                    fontSize: "16px",
                    lineHeight: 1,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  ×
                </button>
              </div>
            </div>

            {/* Drawer body */}
            {!data || (data.sections || []).length === 0 ? (
              <div style={{ textAlign: "center", padding: "40px 16px", color: "var(--color-text-muted)", fontSize: "13px" }}>
                {data?.error || "Summary unavailable right now."}
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
                {(data.sections || []).map((sec, idx) => {
                  const meta = SECTION_META[sec.id] || { icon: "•", title: sec.title };
                  const dot = STANCE_COLOR[sec.stance] || STANCE_COLOR.neutral;
                  return (
                    <section key={idx}>
                      <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px" }}>
                        <span style={{ fontSize: "13px" }}>{meta.icon}</span>
                        <h3
                          style={{
                            fontSize: "11px",
                            fontWeight: 800,
                            textTransform: "uppercase",
                            letterSpacing: "0.08em",
                            color: "var(--color-text-primary)",
                          }}
                        >
                          {sec.title || meta.title}
                        </h3>
                        <span
                          title={`Stance: ${sec.stance}`}
                          style={{
                            width: "6px",
                            height: "6px",
                            borderRadius: "50%",
                            background: dot,
                            marginLeft: "auto",
                          }}
                        />
                      </div>
                      <p
                        style={{
                          fontSize: "13.5px",
                          lineHeight: 1.6,
                          color: "var(--color-text-secondary)",
                          whiteSpace: "pre-wrap",
                        }}
                      >
                        {sec.body}
                      </p>
                      {sec.key_tickers && sec.key_tickers.length > 0 && (
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "5px", marginTop: "8px" }}>
                          {sec.key_tickers.map((t) => (
                            <button
                              key={t}
                              type="button"
                              onClick={() => { setOpen(false); onNavigate?.("company", t); }}
                              style={{
                                padding: "2px 7px",
                                borderRadius: "5px",
                                background: "rgba(99,102,241,0.10)",
                                color: "var(--color-accent-secondary)",
                                border: "1px solid rgba(99,102,241,0.20)",
                                fontSize: "10px",
                                fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                                fontWeight: 700,
                                cursor: "pointer",
                              }}
                            >
                              {t}
                            </button>
                          ))}
                        </div>
                      )}
                    </section>
                  );
                })}
              </div>
            )}

            {data?.disclaimer_short && (
              <p
                style={{
                  fontSize: "10px",
                  color: "var(--color-text-muted)",
                  marginTop: "24px",
                  paddingTop: "16px",
                  borderTop: "1px solid var(--border-subtle)",
                  textAlign: "center",
                  fontStyle: "italic",
                }}
              >
                {data.disclaimer_short}
              </p>
            )}
          </div>
        </div>
      )}
    </>
  );
}
