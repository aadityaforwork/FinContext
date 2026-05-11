"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { supabase } from "../lib/supabase";
import { API_BASE } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Spinner, Skeleton } from "./Loaders";

/**
 * NewsImpactFeed — premium edition
 * ---------------------------------
 * Compact rows. Restrained color. Information-dense. Each row ~88px.
 * Internally scrollable so the surrounding page never grows.
 */

const IMPACT = {
  high:   { color: "#ef4444", label: "HIGH" },
  medium: { color: "#f59e0b", label: "MED"  },
  low:    { color: "#94a3b8", label: "LOW"  },
};

const DIRECTION = {
  positive: { color: "var(--color-accent-green)", arrow: "▲" },
  negative: { color: "var(--color-accent-red)",   arrow: "▼" },
  mixed:    { color: "var(--color-accent-amber)", arrow: "◆" },
};

const CATEGORY_ICON = {
  stock_specific: "📌",
  sector: "🏭",
  macro: "🇮🇳",
  global: "🌍",
};

function NewsRow({ item, onTickerClick }) {
  const dot = IMPACT[item.impact_level] || IMPACT.low;
  const dir = DIRECTION[item.direction] || DIRECTION.mixed;
  const catIcon = CATEGORY_ICON[item.category] || CATEGORY_ICON.macro;

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "auto 1fr",
        gap: "12px",
        padding: "12px 14px",
        background: "transparent",
        borderRadius: "10px",
        border: "1px solid var(--border-subtle)",
        transition: "border-color 0.15s, background 0.15s",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = "rgba(99,102,241,0.04)";
        e.currentTarget.style.borderColor = "rgba(99,102,241,0.20)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = "transparent";
        e.currentTarget.style.borderColor = "var(--border-subtle)";
      }}
    >
      {/* Left rail: impact dot + direction arrow */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: "4px",
          paddingTop: "2px",
          minWidth: "16px",
        }}
      >
        <span
          title={`${dot.label} impact`}
          style={{
            width: "8px",
            height: "8px",
            borderRadius: "50%",
            background: dot.color,
          }}
        />
        <span style={{ color: dir.color, fontSize: "9px", fontWeight: 700 }}>{dir.arrow}</span>
      </div>

      {/* Right: content */}
      <div style={{ minWidth: 0 }}>
        {/* META — single line */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            marginBottom: "4px",
            fontSize: "10px",
            color: "var(--color-text-muted)",
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.04em",
          }}
        >
          <span>{catIcon}</span>
          <span>{dot.label}</span>
          {item.source && (
            <>
              <span style={{ opacity: 0.5 }}>·</span>
              <span style={{ textTransform: "none", fontStyle: "italic", color: "var(--color-text-muted)" }}>
                {item.source}
              </span>
            </>
          )}
        </div>

        {/* HEADLINE */}
        <p
          style={{
            fontSize: "13px",
            fontWeight: 600,
            color: "var(--color-text-primary)",
            lineHeight: 1.4,
            marginBottom: "6px",
          }}
        >
          {item.headline}
        </p>

        {/* AFFECTED + WHY */}
        <div style={{ display: "flex", alignItems: "baseline", gap: "10px", flexWrap: "wrap" }}>
          <div style={{ display: "flex", gap: "4px", flexShrink: 0 }}>
            {(item.affected_tickers || []).slice(0, 3).map((t) => (
              <button
                key={t}
                type="button"
                onClick={(e) => { e.stopPropagation(); onTickerClick?.(t); }}
                style={{
                  padding: "1px 6px",
                  borderRadius: "4px",
                  background: "rgba(99,102,241,0.10)",
                  color: "var(--color-accent-secondary)",
                  border: "1px solid rgba(99,102,241,0.20)",
                  fontSize: "10px",
                  fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                  fontWeight: 700,
                  cursor: "pointer",
                  letterSpacing: "0.02em",
                }}
              >
                {t}
              </button>
            ))}
          </div>
          {item.reason && (
            <p
              style={{
                fontSize: "11.5px",
                color: "var(--color-text-secondary)",
                lineHeight: 1.4,
                margin: 0,
                flex: "1 1 220px",
                minWidth: 0,
              }}
            >
              <span style={{ color: "var(--color-text-muted)" }}>Why: </span>
              {item.reason}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

export default function NewsImpactFeed({ onNavigate }) {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [feed, setFeed] = useState(null);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("all");

  const fetchFeed = useCallback(async (force = false) => {
    if (!user?.id) return;
    if (force) setRefreshing(true); else setLoading(true);
    setError(null);
    try {
      const [{ data: positions }, { data: watchRows }] = await Promise.all([
        supabase.from("portfolio").select("ticker, quantity, buy_price").eq("user_id", user.id),
        supabase.from("watchlist").select("ticker").eq("user_id", user.id),
      ]);
      const res = await fetch(`${API_BASE}/api/intelligence/news-feed`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          positions: positions || [],
          watchlist_tickers: (watchRows || []).map((r) => r.ticker),
          force_refresh: force,
        }),
      });
      if (!res.ok) throw new Error(`Feed request failed (${res.status})`);
      const data = await res.json();
      setFeed(data);
      if (data.error) setError(data.error);
    } catch (e) {
      setError(e?.message || "Could not load news feed");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [user?.id]);

  useEffect(() => { fetchFeed(false); }, [fetchFeed]);

  const items = useMemo(() => {
    const all = feed?.items || [];
    if (filter === "high") return all.filter((i) => i.impact_level === "high");
    return all;
  }, [feed, filter]);

  const handleTickerClick = (t) => onNavigate?.("company", t);

  return (
    <div
      className="dash-news-feed"
      style={{
        background: "var(--color-bg-card)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "12px",
        padding: "14px 16px 16px",
        height: "100%",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* HEADER */}
      <div
        className="dnf-header"
        style={{
          paddingBottom: "12px",
          marginBottom: "10px",
          borderBottom: "1px solid var(--border-subtle)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "12px",
          flexWrap: "wrap",
        }}
      >
        <div>
          <h2
            style={{
              fontSize: "13px",
              fontWeight: 800,
              color: "var(--color-text-primary)",
              letterSpacing: "-0.005em",
              display: "flex",
              alignItems: "center",
              gap: "8px",
            }}
          >
            <span style={{ fontSize: "13px" }}>📡</span>
            News hitting your portfolio
          </h2>
          <p style={{ fontSize: "10px", color: "var(--color-text-muted)", marginTop: "3px", letterSpacing: "0.02em" }}>
            {feed?.demo_mode
              ? "Sample feed — add holdings for live personalization"
              : `${items.length} ${items.length === 1 ? "item" : "items"} scored against your universe`}
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <div
            style={{
              display: "flex",
              border: "1px solid var(--border-subtle)",
              borderRadius: "6px",
              overflow: "hidden",
            }}
          >
            {[
              { id: "all",  label: "All"  },
              { id: "high", label: "High" },
            ].map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => setFilter(f.id)}
                style={{
                  padding: "5px 10px",
                  fontSize: "10px",
                  fontWeight: 700,
                  border: "none",
                  background: filter === f.id ? "rgba(99,102,241,0.12)" : "transparent",
                  color: filter === f.id ? "var(--color-accent-secondary)" : "var(--color-text-muted)",
                  cursor: "pointer",
                  letterSpacing: "0.02em",
                }}
              >
                {f.label}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => fetchFeed(true)}
            disabled={refreshing}
            aria-label="Refresh"
            style={{
              padding: "5px 10px",
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
        </div>
      </div>

      {/* BODY */}
      <div style={{ flex: 1, overflowY: "auto", paddingRight: "4px" }}>
        {loading ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {[1, 2, 3, 4, 5].map((i) => <Skeleton key={i} h={88} r={10} />)}
          </div>
        ) : items.length === 0 ? (
          <div
            style={{
              padding: "40px 16px",
              textAlign: "center",
              color: "var(--color-text-muted)",
              fontSize: "12px",
            }}
          >
            {error ? (
              <>
                <p style={{ marginBottom: "10px" }}>{error}</p>
                <button
                  type="button"
                  onClick={() => fetchFeed(true)}
                  style={{
                    padding: "6px 12px",
                    borderRadius: "6px",
                    border: "none",
                    background: "rgba(99,102,241,0.15)",
                    color: "var(--color-accent-secondary)",
                    fontSize: "11px",
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  Try again
                </button>
              </>
            ) : (
              <>
                <span style={{ fontSize: "22px", display: "block", marginBottom: "6px" }}>🌤️</span>
                {filter === "high"
                  ? "No high-impact items right now."
                  : "Markets are quiet on your universe."}
              </>
            )}
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {items.map((item, i) => (
              <NewsRow key={item.news_id || i} item={item} onTickerClick={handleTickerClick} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
