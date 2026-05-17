"use client";

import { useState, useEffect, useCallback } from "react";
import { supabase } from "../lib/supabase";
import { API_BASE } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useToast } from "./Toast";
import { Spinner, Skeleton } from "./Loaders";
import Drawer from "./Drawer";

/**
 * WatchlistDrawer — lightweight watchlist manager.
 * Lists tickets with live change %, remove button, and a CTA to open the
 * Screener drawer for adding more.
 */
export default function WatchlistDrawer({ open, onClose, onNavigate, onOpenScreener }) {
  const { user } = useAuth();
  const toast = useToast();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchAll = useCallback(async () => {
    if (!user?.id || !open) return;
    setLoading(true);
    try {
      const { data: rows } = await supabase
        .from("watchlist")
        .select("ticker, added_at")
        .eq("user_id", user.id)
        .order("added_at", { ascending: false });

      if (!rows || rows.length === 0) { setItems([]); return; }

      let priceMap = {};
      try {
        const res = await fetch(`${API_BASE}/api/watchlist/prices`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tickers: rows.map((r) => r.ticker) }),
        });
        if (res.ok) priceMap = await res.json();
      } catch { /* show without prices */ }

      setItems(rows.map((r) => ({
        ticker: r.ticker,
        name: priceMap[r.ticker]?.name ?? r.ticker,
        sector: priceMap[r.ticker]?.sector ?? "—",
        change_percent: priceMap[r.ticker]?.change_percent,
      })));
    } finally {
      setLoading(false);
    }
  }, [user?.id, open]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const remove = async (ticker) => {
    if (!user?.id) return;
    await supabase
      .from("watchlist")
      .delete()
      .eq("ticker", ticker)
      .eq("user_id", user.id);
    setItems((prev) => prev.filter((i) => i.ticker !== ticker));
    toast.success(`${ticker} removed from watchlist`);
  };

  const drawerActions = (
    <button
      type="button"
      onClick={() => { onClose(); onOpenScreener?.(); }}
      style={{
        padding: "5px 11px",
        borderRadius: "6px",
        border: "none",
        background: "rgba(99,102,241,0.15)",
        color: "var(--color-accent-secondary)",
        fontSize: "11px",
        fontWeight: 700,
        cursor: "pointer",
      }}
    >
      + Add
    </button>
  );

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title="Watchlist"
      subtitle={loading ? "Loading…" : `${items.length} ${items.length === 1 ? "stock" : "stocks"} tracked`}
      actions={drawerActions}
      width="min(520px, 92vw)"
    >
      {loading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} h={62} r={10} />)}
        </div>
      ) : items.length === 0 ? (
        <div style={{ padding: "40px 16px", textAlign: "center" }}>
          <span style={{ fontSize: "36px", display: "block", marginBottom: "10px" }}>⭐</span>
          <p style={{ fontSize: "14px", fontWeight: 600, color: "var(--color-text-secondary)" }}>
            Your watchlist is empty
          </p>
          <p style={{ fontSize: "12px", color: "var(--color-text-muted)", marginTop: "6px", marginBottom: "16px" }}>
            Find stocks via the Screener and add them here.
          </p>
          <button
            type="button"
            onClick={() => { onClose(); onOpenScreener?.(); }}
            style={{
              padding: "8px 16px",
              borderRadius: "8px",
              border: "none",
              background: "linear-gradient(135deg, var(--color-accent-primary), var(--color-accent-secondary))",
              color: "white",
              fontSize: "12px",
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            Open Screener
          </button>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          {items.map((it) => {
            const pct = it.change_percent;
            const isUp = pct != null && pct >= 0;
            return (
              <div
                key={it.ticker}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: "10px",
                  padding: "10px 12px",
                  background: "var(--color-bg-card)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "8px",
                }}
              >
                <button
                  type="button"
                  onClick={() => { onClose(); onNavigate?.("company", it.ticker); }}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "flex-start",
                    gap: "2px",
                    background: "transparent",
                    border: "none",
                    cursor: "pointer",
                    padding: 0,
                    flex: 1,
                    minWidth: 0,
                    textAlign: "left",
                  }}
                >
                  <span
                    style={{
                      fontSize: "12.5px",
                      fontWeight: 700,
                      color: "var(--color-text-primary)",
                      fontFamily: "var(--font-mono)",
                    }}
                  >
                    {it.ticker}
                  </span>
                  <span
                    style={{
                      fontSize: "11px",
                      color: "var(--color-text-muted)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      maxWidth: "260px",
                    }}
                  >
                    {it.name} {it.sector !== "—" && `· ${it.sector}`}
                  </span>
                </button>
                <span
                  style={{
                    fontSize: "12px",
                    fontWeight: 700,
                    fontFamily: "var(--font-mono)",
                    color: pct == null
                      ? "var(--color-text-muted)"
                      : isUp
                        ? "var(--color-accent-green)"
                        : "var(--color-accent-red)",
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {pct == null ? "—" : `${isUp ? "+" : ""}${pct.toFixed(1)}%`}
                </span>
                <button
                  type="button"
                  onClick={() => remove(it.ticker)}
                  aria-label={`Remove ${it.ticker}`}
                  style={{
                    width: "24px",
                    height: "24px",
                    borderRadius: "6px",
                    border: "1px solid var(--border-subtle)",
                    background: "transparent",
                    color: "var(--color-text-muted)",
                    cursor: "pointer",
                    fontSize: "14px",
                    lineHeight: 1,
                  }}
                >
                  ×
                </button>
              </div>
            );
          })}
        </div>
      )}
    </Drawer>
  );
}
