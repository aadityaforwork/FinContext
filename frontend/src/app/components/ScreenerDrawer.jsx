"use client";

import { useState, useEffect } from "react";
import { supabase } from "../lib/supabase";
import { API_BASE } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useToast } from "./Toast";
import { Spinner, Skeleton } from "./Loaders";
import Drawer from "./Drawer";

/**
 * ScreenerDrawer — lightweight stock finder.
 * Search + sector filter + compact result rows. Click a result to view its
 * company page; click "+" to add to watchlist instantly.
 */
export default function ScreenerDrawer({ open, onClose, onNavigate }) {
  const { user } = useAuth();
  const toast = useToast();
  const [sectors, setSectors] = useState([]);
  const [stocks, setStocks] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [selectedSector, setSelectedSector] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!open) return;
    fetch(`${API_BASE}/api/stocks/sectors`)
      .then((r) => (r.ok ? r.json() : []))
      .then(setSectors)
      .catch(() => {});
  }, [open]);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(searchQuery), 300);
    return () => clearTimeout(t);
  }, [searchQuery]);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    const controller = new AbortController();
    const params = new URLSearchParams();
    if (debouncedQuery) params.set("q", debouncedQuery);
    if (selectedSector) params.set("sector", selectedSector);
    params.set("limit", "50");

    fetch(`${API_BASE}/api/stocks/search?${params}`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => { setStocks(data || []); setLoading(false); })
      .catch((err) => { if (err.name !== "AbortError") setLoading(false); });

    return () => controller.abort();
  }, [open, debouncedQuery, selectedSector]);

  const addToWatchlist = async (ticker) => {
    if (!user?.id) { toast.error("Please sign in."); return; }
    const { error } = await supabase
      .from("watchlist")
      .upsert({ ticker, user_id: user.id }, { onConflict: "ticker,user_id", ignoreDuplicates: true });
    if (error) toast.error(`Failed to add ${ticker}`);
    else toast.success(`${ticker} added to watchlist`);
  };

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title="Find stocks"
      subtitle="Search the NSE universe, add to watchlist, or open company view"
      width="min(580px, 92vw)"
    >
      {/* SEARCH + FILTER */}
      <div style={{ display: "flex", gap: "8px", marginBottom: "14px" }}>
        <input
          type="text"
          autoFocus
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search ticker or company name…"
          style={{
            flex: 1,
            padding: "10px 12px",
            borderRadius: "8px",
            border: "1px solid var(--border-subtle)",
            background: "var(--color-bg-card)",
            color: "var(--color-text-primary)",
            fontSize: "13px",
            outline: "none",
          }}
        />
        <select
          value={selectedSector}
          onChange={(e) => setSelectedSector(e.target.value)}
          style={{
            padding: "10px 10px",
            borderRadius: "8px",
            border: "1px solid var(--border-subtle)",
            background: "var(--color-bg-card)",
            color: "var(--color-text-primary)",
            fontSize: "12px",
            outline: "none",
            cursor: "pointer",
            maxWidth: "180px",
          }}
        >
          <option value="">All sectors</option>
          {sectors.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      {/* RESULTS */}
      {loading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          {[1, 2, 3, 4, 5, 6].map((i) => <Skeleton key={i} h={48} r={8} />)}
        </div>
      ) : stocks.length === 0 ? (
        <div style={{ padding: "32px 16px", textAlign: "center", color: "var(--color-text-muted)", fontSize: "12px" }}>
          No stocks match those filters.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
          {stocks.map((s) => {
            const pct = s.change_percent;
            const isUp = pct != null && pct >= 0;
            return (
              <div
                key={s.ticker}
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr auto auto",
                  alignItems: "center",
                  gap: "10px",
                  padding: "9px 12px",
                  background: "var(--color-bg-card)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "8px",
                }}
              >
                <button
                  type="button"
                  onClick={() => { onClose(); onNavigate?.("company", s.ticker); }}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "flex-start",
                    background: "transparent",
                    border: "none",
                    cursor: "pointer",
                    padding: 0,
                    minWidth: 0,
                    textAlign: "left",
                    overflow: "hidden",
                  }}
                >
                  <span
                    style={{
                      fontSize: "12px",
                      fontWeight: 700,
                      color: "var(--color-text-primary)",
                      fontFamily: "var(--font-mono)",
                    }}
                  >
                    {s.ticker}
                  </span>
                  <span
                    style={{
                      fontSize: "10.5px",
                      color: "var(--color-text-muted)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      maxWidth: "300px",
                    }}
                  >
                    {s.name} · {s.sector}
                  </span>
                </button>
                <span
                  style={{
                    fontSize: "11px",
                    fontWeight: 600,
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
                  onClick={() => addToWatchlist(s.ticker)}
                  aria-label={`Add ${s.ticker} to watchlist`}
                  title="Add to watchlist"
                  style={{
                    width: "26px",
                    height: "26px",
                    borderRadius: "6px",
                    border: "1px solid rgba(99,102,241,0.25)",
                    background: "rgba(99,102,241,0.10)",
                    color: "var(--color-accent-secondary)",
                    cursor: "pointer",
                    fontSize: "14px",
                    fontWeight: 700,
                    lineHeight: 1,
                  }}
                >
                  +
                </button>
              </div>
            );
          })}
        </div>
      )}
    </Drawer>
  );
}
