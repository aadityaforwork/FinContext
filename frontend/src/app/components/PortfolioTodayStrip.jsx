"use client";

import { useState, useEffect, useCallback } from "react";
import { supabase } from "../lib/supabase";
import { API_BASE } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Spinner } from "./Loaders";

/**
 * PortfolioTodayStrip
 * -------------------
 * Single-row premium hero. Numbers in monospaced, no gradient, no header label
 * stack — the data IS the headline. ~52px tall.
 */

const DEMO_DATA = {
  total_pnl: 8430,
  total_pnl_percent: 1.2,
  current_value: 712430,
  positions: [
    { ticker: "INFY",       change_percent: 2.1 },
    { ticker: "TCS",        change_percent: 1.8 },
    { ticker: "RELIANCE",   change_percent: -0.4 },
    { ticker: "HDFCBANK",   change_percent: 0.8 },
    { ticker: "TATAMOTORS", change_percent: -3.0 },
  ],
};

function formatINR(n) {
  if (n == null || isNaN(n)) return "—";
  const sign = n >= 0 ? "+" : "−";
  return `${sign}₹${Math.abs(n).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

function Mover({ position, type }) {
  const isUp = type === "up";
  const color = isUp ? "var(--color-accent-green)" : "var(--color-accent-red)";
  const arrow = isUp ? "▲" : "▼";
  const pct = position?.change_percent;
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "6px",
        fontSize: "12px",
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
      }}
    >
      <span style={{ color, fontSize: "9px" }}>{arrow}</span>
      <span style={{ color: "var(--color-text-primary)", fontWeight: 600 }}>
        {position?.ticker || "—"}
      </span>
      <span style={{ color, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
        {pct != null ? `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%` : "—"}
      </span>
    </div>
  );
}

export default function PortfolioTodayStrip({ onNavigate }) {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [demoMode, setDemoMode] = useState(false);

  const fetchData = useCallback(async () => {
    if (!user?.id) return;
    setLoading(true);
    try {
      const { data: rows } = await supabase
        .from("portfolio")
        .select("ticker, quantity, buy_price")
        .eq("user_id", user.id);

      if (!rows || rows.length === 0) {
        setData(DEMO_DATA);
        setDemoMode(true);
        return;
      }
      try {
        const res = await fetch(`${API_BASE}/api/portfolio/enrich`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ positions: rows }),
        });
        if (res.ok) { setData(await res.json()); setDemoMode(false); }
        else {
          setData({
            total_pnl: 0, total_pnl_percent: 0, current_value: 0,
            positions: rows.map((r) => ({ ticker: r.ticker, change_percent: null })),
          });
          setDemoMode(false);
        }
      } catch {
        setData({
          total_pnl: 0, total_pnl_percent: 0, current_value: 0,
          positions: rows.map((r) => ({ ticker: r.ticker, change_percent: null })),
        });
        setDemoMode(false);
      }
    } finally {
      setLoading(false);
    }
  }, [user?.id]);

  useEffect(() => { fetchData(); }, [fetchData]);

  if (loading) {
    return (
      <div
        className="dash-strip"
        style={{
          padding: "14px 20px",
          borderRadius: "12px",
          background: "var(--color-bg-card)",
          border: "1px solid var(--border-subtle)",
          display: "flex",
          alignItems: "center",
          gap: "12px",
        }}
      >
        <Spinner size="sm" />
        <span style={{ fontSize: "12px", color: "var(--color-text-muted)" }}>
          Computing your P&amp;L…
        </span>
      </div>
    );
  }

  if (!data) return null;

  const positions = data.positions || [];
  const sortedByMove = [...positions].sort((a, b) => (b.change_percent || 0) - (a.change_percent || 0));
  const topUp = sortedByMove.find((p) => (p.change_percent || 0) > 0);
  const topDown = [...sortedByMove].reverse().find((p) => (p.change_percent || 0) < 0);
  const pnl = data.total_pnl ?? 0;
  const pnlPct = data.total_pnl_percent ?? 0;
  const isPositive = pnl >= 0;
  const accent = isPositive ? "var(--color-accent-green)" : "var(--color-accent-red)";

  return (
    <div
      className="dash-strip dash-portfolio-strip"
      style={{
        padding: "14px 20px",
        borderRadius: "12px",
        background: "var(--color-bg-card)",
        border: "1px solid var(--border-subtle)",
        borderLeft: `3px solid ${accent}`,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "20px",
        flexWrap: "wrap",
      }}
    >
      {/* LEFT — P&L */}
      <div className="dps-pnl" style={{ display: "flex", alignItems: "center", gap: "16px" }}>
        <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.1 }}>
          <span
            style={{
              fontSize: "9px",
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: "0.10em",
              color: "var(--color-text-muted)",
              marginBottom: "2px",
            }}
          >
            Portfolio today
          </span>
          <div style={{ display: "flex", alignItems: "baseline", gap: "8px" }}>
            <span
              style={{
                fontSize: "22px",
                fontWeight: 700,
                color: accent,
                fontVariantNumeric: "tabular-nums",
                fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                letterSpacing: "-0.01em",
              }}
            >
              {formatINR(pnl)}
            </span>
            <span
              style={{
                fontSize: "13px",
                fontWeight: 600,
                color: accent,
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%
            </span>
          </div>
        </div>
        {demoMode && (
          <span
            style={{
              fontSize: "9px",
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: "0.06em",
              padding: "2px 7px",
              borderRadius: "9999px",
              background: "rgba(245,158,11,0.12)",
              color: "var(--color-accent-amber)",
              border: "1px solid rgba(245,158,11,0.25)",
            }}
          >
            Sample
          </span>
        )}
      </div>

      {/* MIDDLE — top mover / loser, compact */}
      <div className="dps-movers" style={{ display: "flex", alignItems: "center", gap: "20px", flex: 1, justifyContent: "center" }}>
        {topUp && <Mover position={topUp} type="up" />}
        {topUp && topDown && (
          <span style={{ width: "1px", height: "16px", background: "var(--border-subtle)" }} />
        )}
        {topDown && <Mover position={topDown} type="down" />}
      </div>

      {/* RIGHT — CTAs */}
      <div className="dps-cta-group" style={{ display: "flex", gap: "6px", flexShrink: 0 }}>
        <button
          type="button"
          onClick={() => onNavigate?.("analysis")}
          className="dps-cta dps-cta-primary"
          style={{
            padding: "7px 13px",
            borderRadius: "8px",
            border: "none",
            background:
              "linear-gradient(135deg, var(--color-accent-primary), var(--color-accent-cyan))",
            color: "white",
            fontSize: "11px",
            fontWeight: 700,
            cursor: "pointer",
            letterSpacing: "0.02em",
            whiteSpace: "nowrap",
          }}
        >
          🧠 Run AI Analysis
        </button>
        <button
          type="button"
          onClick={() => onNavigate?.("portfolio")}
          className="dps-cta"
          style={{
            padding: "7px 13px",
            borderRadius: "8px",
            border: "1px solid var(--border-subtle)",
            background: "transparent",
            color: "var(--color-text-secondary)",
            fontSize: "11px",
            fontWeight: 600,
            cursor: "pointer",
            letterSpacing: "0.02em",
            whiteSpace: "nowrap",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "rgba(99,102,241,0.08)";
            e.currentTarget.style.borderColor = "rgba(99,102,241,0.3)";
            e.currentTarget.style.color = "var(--color-accent-secondary)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "transparent";
            e.currentTarget.style.borderColor = "var(--border-subtle)";
            e.currentTarget.style.color = "var(--color-text-secondary)";
          }}
        >
          Details →
        </button>
      </div>
    </div>
  );
}
