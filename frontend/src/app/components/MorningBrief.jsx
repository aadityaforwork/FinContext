"use client";

import { useState, useEffect, useCallback } from "react";
import { supabase } from "../lib/supabase";
import { API_BASE } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Spinner, Skeleton, LoaderHeader } from "./Loaders";
import { claimText, claimSource } from "../lib/claim";

const CATEGORY_META = {
  macro: { icon: "🌐", label: "Macro" },
  sector: { icon: "🏭", label: "Sector" },
  stock_specific: { icon: "📌", label: "Stock" },
  global: { icon: "🌍", label: "Global" },
  earnings: { icon: "📊", label: "Earnings" },
};

const STANCE_STYLES = {
  tailwind:  { color: "var(--color-accent-green)", bg: "rgba(16,185,129,0.10)", label: "Tailwind", arrow: "↑" },
  headwind:  { color: "var(--color-accent-red)",   bg: "rgba(239,68,68,0.10)",   label: "Headwind", arrow: "↓" },
  watch:     { color: "var(--color-accent-amber)", bg: "rgba(245,158,11,0.10)",  label: "Watch",    arrow: "•"  },
  neutral:   { color: "var(--color-text-muted)",   bg: "rgba(148,163,184,0.08)", label: "Neutral",  arrow: "·"  },
};

function formatTime(isoString) {
  if (!isoString) return "";
  try {
    const d = new Date(isoString);
    return d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: true });
  } catch {
    return "";
  }
}

export default function MorningBrief({ onNavigate }) {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [brief, setBrief] = useState(null);
  const [error, setError] = useState(null);

  const fetchBrief = useCallback(async (force = false) => {
    if (!user?.id) return;
    if (force) setRefreshing(true); else setLoading(true);
    setError(null);

    try {
      // 1. Pull user's positions + watchlist from Supabase
      const [{ data: positions }, { data: watchRows }] = await Promise.all([
        supabase
          .from("portfolio")
          .select("ticker, quantity, buy_price")
          .eq("user_id", user.id),
        supabase
          .from("watchlist")
          .select("ticker")
          .eq("user_id", user.id),
      ]);

      // 2. Call the brief endpoint
      const res = await fetch(`${API_BASE}/api/intelligence/morning-brief`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          positions: positions || [],
          watchlist_tickers: (watchRows || []).map((r) => r.ticker),
          force_refresh: force,
        }),
      });

      if (!res.ok) {
        throw new Error(`Brief request failed (${res.status})`);
      }
      const data = await res.json();
      setBrief(data);
      if (data.error) setError(data.error);
    } catch (e) {
      setError(e?.message || "Could not load brief");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [user?.id]);

  useEffect(() => { fetchBrief(false); }, [fetchBrief]);

  // ----- Loading -----
  if (loading) {
    return (
      <div className="glass-card animate-fade-in" style={{ padding: "24px", marginBottom: "24px" }}>
        <LoaderHeader label="Reading overnight markets and your holdings…" />
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} h={64} r={12} />
          ))}
        </div>
      </div>
    );
  }

  // ----- Hard error (no payload at all) -----
  if (!brief) {
    return (
      <div className="glass-card" style={{ padding: "20px", marginBottom: "24px", textAlign: "center" }}>
        <p style={{ fontSize: "13px", color: "var(--color-text-muted)" }}>
          {error || "Morning brief unavailable right now."}
        </p>
        <button
          onClick={() => fetchBrief(true)}
          style={{
            marginTop: "12px", padding: "8px 18px", borderRadius: "8px", border: "none",
            background: "rgba(99,102,241,0.15)", color: "var(--color-accent-secondary)",
            fontSize: "13px", fontWeight: 600, cursor: "pointer",
          }}
        >
          Try again
        </button>
      </div>
    );
  }

  const items = brief.items || [];
  const generatedAt = formatTime(brief.generated_at);

  return (
    <div
      className="glass-card animate-fade-in"
      style={{
        padding: "24px",
        marginBottom: "24px",
        background:
          "linear-gradient(135deg, rgba(99,102,241,0.08), rgba(6,182,212,0.04))",
        border: "1px solid rgba(99,102,241,0.18)",
      }}
    >
      {/* ---- Header ---- */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "12px", marginBottom: "18px" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "4px" }}>
            <span style={{ fontSize: "20px" }}>☀️</span>
            <h2 className="gradient-text" style={{ fontSize: "20px", fontWeight: 800, letterSpacing: "-0.01em" }}>
              Your Morning Brief
            </h2>
          </div>
          <p style={{ fontSize: "12px", color: "var(--color-text-muted)" }}>
            {brief.demo_mode
              ? "Sample brief — add holdings or watchlist for personalized insights"
              : `Personalized for ${brief.user_universe?.holdings_count || 0} holdings, ${brief.user_universe?.watchlist_count || 0} on watchlist`}
            {generatedAt ? ` · Generated ${generatedAt}` : ""}
          </p>
        </div>
        <button
          type="button"
          onClick={() => fetchBrief(true)}
          disabled={refreshing}
          aria-label="Refresh brief"
          style={{
            display: "flex", alignItems: "center", gap: "8px",
            padding: "8px 14px", borderRadius: "8px", border: "1px solid var(--border-subtle)",
            background: "var(--color-bg-card)", color: "var(--color-text-secondary)",
            fontSize: "12px", fontWeight: 600, cursor: refreshing ? "wait" : "pointer",
            opacity: refreshing ? 0.7 : 1,
          }}
        >
          {refreshing ? <Spinner size="sm" /> : <span style={{ fontSize: "13px" }}>↻</span>}
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {/* ---- Demo banner ---- */}
      {brief.demo_mode && (
        <div
          style={{
            padding: "10px 14px", marginBottom: "16px", borderRadius: "10px",
            background: "rgba(245,158,11,0.10)", border: "1px solid rgba(245,158,11,0.25)",
            fontSize: "12px", color: "var(--color-accent-amber)", display: "flex", gap: "8px", alignItems: "center",
          }}
        >
          <span style={{ fontSize: "14px" }}>👋</span>
          <span>Showing a sample portfolio (INFY, TCS, RELIANCE, HDFCBANK, TATAMOTORS) so you can see how this works.</span>
        </div>
      )}

      {/* ---- Items ---- */}
      {items.length === 0 ? (
        <p style={{ fontSize: "13px", color: "var(--color-text-muted)", padding: "16px 0" }}>
          {error || "Nothing material to flag right now — markets are quiet on your universe."}
        </p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          {items.map((item, i) => {
            const cat = CATEGORY_META[item.category] || CATEGORY_META.macro;
            const stance = STANCE_STYLES[item.stance] || STANCE_STYLES.neutral;
            return (
              <div
                key={i}
                style={{
                  padding: "14px 16px",
                  background: "rgba(15,23,42,0.4)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "12px",
                  borderLeft: `3px solid ${stance.color}`,
                  transition: "border-color 0.2s",
                }}
              >
                <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "12px", marginBottom: "6px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <span style={{ fontSize: "15px" }}>{cat.icon}</span>
                    <span style={{
                      fontSize: "10px", fontWeight: 700, textTransform: "uppercase",
                      letterSpacing: "0.05em", color: "var(--color-text-muted)",
                    }}>
                      {cat.label}
                    </span>
                  </div>
                  <span style={{
                    fontSize: "10px", fontWeight: 700, padding: "2px 8px",
                    borderRadius: "9999px", background: stance.bg, color: stance.color,
                    textTransform: "uppercase", letterSpacing: "0.05em",
                  }}>
                    {stance.arrow} {stance.label}
                  </span>
                </div>
                <p style={{ fontSize: "14px", fontWeight: 600, color: "var(--color-text-primary)", marginBottom: "4px", lineHeight: 1.4 }}>
                  {item.headline}
                </p>
                <p
                  title={claimSource(item.body) || ""}
                  style={{ fontSize: "13px", color: "var(--color-text-secondary)", lineHeight: 1.5 }}
                >
                  {claimText(item.body)}
                </p>
                {item.affected_tickers && item.affected_tickers.length > 0 && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginTop: "10px" }}>
                    {item.affected_tickers.map((t) => (
                      <button
                        key={t}
                        type="button"
                        onClick={() => onNavigate?.("company", t)}
                        style={{
                          padding: "3px 10px", borderRadius: "6px",
                          background: "rgba(99,102,241,0.12)",
                          color: "var(--color-accent-secondary)",
                          border: "1px solid rgba(99,102,241,0.20)",
                          fontSize: "11px", fontWeight: 600, cursor: "pointer",
                        }}
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* ---- Compliance footnote ---- */}
      {brief.disclaimer_short && (
        <p style={{
          fontSize: "10px", color: "var(--color-text-muted)", marginTop: "16px",
          textAlign: "center", fontStyle: "italic",
        }}>
          {brief.disclaimer_short}
        </p>
      )}
    </div>
  );
}
