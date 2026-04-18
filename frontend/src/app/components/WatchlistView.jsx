"use client";

import { useState, useEffect, useCallback } from "react";
import { supabase } from "../lib/supabase";
import { API_BASE as _SHARED_API_BASE } from "../lib/api";
const API_BASE = _SHARED_API_BASE;

export default function WatchlistView({ onNavigate }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchWatchlist = useCallback(async () => {
    setLoading(true);
    try {
      // 1. Get tickers from Supabase
      const { data: rows, error } = await supabase
        .from("watchlist")
        .select("ticker, added_at")
        .order("added_at", { ascending: false });

      if (error) throw error;
      if (!rows || rows.length === 0) { setItems([]); return; }

      // 2. Enrich with live prices from backend
      const res = await fetch(`${API_BASE}/api/watchlist/prices`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tickers: rows.map((r) => r.ticker) }),
      });
      const priceMap = res.ok ? await res.json() : {};

      setItems(rows.map((r) => ({
        ticker: r.ticker,
        added_at: r.added_at,
        name: priceMap[r.ticker]?.name ?? r.ticker,
        sector: priceMap[r.ticker]?.sector ?? "—",
        current_price: priceMap[r.ticker]?.current_price ?? 0,
        change_percent: priceMap[r.ticker]?.change_percent ?? 0,
      })));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchWatchlist(); }, [fetchWatchlist]);

  const removeItem = async (ticker) => {
    await supabase.from("watchlist").delete().eq("ticker", ticker);
    setItems((prev) => prev.filter((i) => i.ticker !== ticker));
  };

  return (
    <div>
      <div className="section-header">
        <div>
          <h2 style={{ fontSize: "24px", fontWeight: 700, color: "var(--color-text-primary)" }}>Watchlist</h2>
          <p style={{ fontSize: "13px", color: "var(--color-text-muted)", marginTop: "4px" }}>
            {items.length} stocks tracked
          </p>
        </div>
        <button onClick={() => onNavigate?.("screener")}
          style={{ padding: "8px 16px", borderRadius: "10px", fontSize: "13px", fontWeight: 500, border: "none",
            cursor: "pointer", background: "rgba(99,102,241,0.2)", color: "var(--color-accent-secondary)" }}>
          + Add Stocks
        </button>
      </div>

      {loading ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "16px" }}>
          {[1, 2, 3, 4].map((i) => <div key={i} className="shimmer" style={{ height: "140px", borderRadius: "16px" }} />)}
        </div>
      ) : items.length === 0 ? (
        <div className="glass-card" style={{ padding: "60px 24px", textAlign: "center" }}>
          <span style={{ fontSize: "48px", display: "block", marginBottom: "16px" }}>⭐</span>
          <p style={{ fontSize: "16px", fontWeight: 600, color: "var(--color-text-secondary)" }}>Your watchlist is empty</p>
          <p style={{ fontSize: "13px", color: "var(--color-text-muted)", marginTop: "8px" }}>Use the Screener to find and add stocks</p>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "16px" }}>
          {items.map((stock) => {
            const isPos = stock.change_percent >= 0;
            return (
              <div key={stock.ticker} className="glass-card animate-fade-in"
                style={{ padding: "20px", cursor: "pointer", transition: "all 0.3s", position: "relative" }}
                onClick={() => onNavigate?.("analysis", stock.ticker)}
                onMouseEnter={(e) => { e.currentTarget.style.borderColor = "var(--border-active)"; e.currentTarget.style.boxShadow = "var(--shadow-glow)"; }}
                onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--border-subtle)"; e.currentTarget.style.boxShadow = "none"; }}>
                <button onClick={(e) => { e.stopPropagation(); removeItem(stock.ticker); }}
                  style={{ position: "absolute", top: "12px", right: "12px", width: "24px", height: "24px",
                    borderRadius: "6px", border: "none", background: "rgba(239,68,68,0.1)",
                    color: "var(--color-accent-red)", cursor: "pointer", fontSize: "12px",
                    display: "flex", alignItems: "center", justifyContent: "center" }}>✕</button>

                <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px" }}>
                  <span style={{ fontSize: "15px", fontWeight: 700, color: "var(--color-text-primary)" }}>{stock.ticker}</span>
                  <span style={{ padding: "2px 8px", borderRadius: "4px", fontSize: "10px", fontWeight: 500,
                    background: "rgba(99,102,241,0.15)", color: "var(--color-accent-secondary)" }}>{stock.sector}</span>
                </div>
                <p style={{ fontSize: "12px", color: "var(--color-text-muted)", marginBottom: "16px" }}>{stock.name}</p>

                <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
                  <span style={{ fontSize: "22px", fontWeight: 700, fontVariantNumeric: "tabular-nums", color: "var(--color-text-primary)" }}>
                    {stock.current_price > 0 ? `₹${stock.current_price.toLocaleString("en-IN", { minimumFractionDigits: 2 })}` : "—"}
                  </span>
                  <span style={{ fontSize: "14px", fontWeight: 600, fontVariantNumeric: "tabular-nums",
                    color: isPos ? "var(--color-accent-green)" : "var(--color-accent-red)" }}>
                    {isPos ? "▲" : "▼"} {isPos ? "+" : ""}{stock.change_percent.toFixed(2)}%
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
