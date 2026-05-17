"use client";

import { useState, useEffect, useCallback } from "react";
import { supabase } from "../lib/supabase";
import { API_BASE } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Spinner } from "./Loaders";
import { SearchIcon, TargetIcon } from "./Icons";

/**
 * UniverseRail — premium tabbed rail.
 * Three tabs: Holdings | Watchlist | Indices. Switching is one click —
 * users with 40 holdings can reach their watchlist without scrolling.
 * Footer: quick actions to open Screener and Watchlist drawers.
 */

const DEMO_HOLDINGS = [
  { ticker: "INFY",       change_percent: 2.1 },
  { ticker: "TCS",        change_percent: 1.8 },
  { ticker: "RELIANCE",   change_percent: -0.4 },
  { ticker: "HDFCBANK",   change_percent: 0.8 },
  { ticker: "TATAMOTORS", change_percent: -3.0 },
];
const DEMO_WATCHLIST = [
  { ticker: "BAJFINANCE", change_percent: 0.5 },
  { ticker: "ITC",        change_percent: -0.2 },
  { ticker: "ASIANPAINT", change_percent: 1.1 },
];

function ChangeCell({ pct }) {
  if (pct == null) {
    return (
      <span style={{ fontSize: "11px", color: "var(--color-text-muted)", fontFamily: "var(--font-mono)" }}>
        —
      </span>
    );
  }
  const isUp = pct >= 0;
  return (
    <span
      style={{
        fontSize: "11px",
        fontWeight: 600,
        color: isUp ? "var(--color-accent-green)" : "var(--color-accent-red)",
        fontFamily: "var(--font-mono)",
        fontVariantNumeric: "tabular-nums",
      }}
    >
      {isUp ? "+" : ""}{pct.toFixed(1)}%
    </span>
  );
}

function Row({ ticker, change_percent, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        width: "100%",
        padding: "5px 10px",
        borderRadius: "5px",
        border: "none",
        background: "transparent",
        color: "var(--color-text-primary)",
        cursor: "pointer",
        transition: "background 0.12s",
        lineHeight: 1.2,
        font: "inherit",
        margin: 0,
      }}
      onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(99,102,241,0.06)")}
      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
    >
      <span
        style={{
          fontSize: "11.5px",
          fontWeight: 600,
          fontFamily: "var(--font-mono)",
          letterSpacing: "0.01em",
          lineHeight: 1.2,
        }}
      >
        {ticker}
      </span>
      <ChangeCell pct={change_percent} />
    </button>
  );
}

export default function UniverseRail({
  onNavigate,
  onOpenWatchlist,
  onOpenScreener,
  onOpenPortfolio,
}) {
  const { user } = useAuth();
  const [holdings, setHoldings] = useState([]);
  const [watchlist, setWatchlist] = useState([]);
  const [sectors, setSectors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [demoMode, setDemoMode] = useState(false);
  const [tab, setTab] = useState("holdings");

  const fetchAll = useCallback(async () => {
    if (!user?.id) return;
    setLoading(true);
    try {
      const [{ data: holdRows }, { data: watchRows }] = await Promise.all([
        supabase.from("portfolio").select("ticker, quantity, buy_price").eq("user_id", user.id),
        supabase.from("watchlist").select("ticker").eq("user_id", user.id),
      ]);

      const isEmpty = (!holdRows || holdRows.length === 0) && (!watchRows || watchRows.length === 0);
      if (isEmpty) {
        setHoldings(DEMO_HOLDINGS);
        setWatchlist(DEMO_WATCHLIST);
        setDemoMode(true);
      } else {
        setDemoMode(false);

        if (holdRows && holdRows.length > 0) {
          try {
            const res = await fetch(`${API_BASE}/api/portfolio/enrich`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ positions: holdRows }),
            });
            if (res.ok) {
              const data = await res.json();
              setHoldings(
                (data.positions || []).map((p) => ({
                  ticker: p.ticker,
                  change_percent: p.change_percent ?? null,
                }))
              );
            } else {
              setHoldings(holdRows.map((r) => ({ ticker: r.ticker, change_percent: null })));
            }
          } catch {
            setHoldings(holdRows.map((r) => ({ ticker: r.ticker, change_percent: null })));
          }
        } else {
          setHoldings([]);
        }

        if (watchRows && watchRows.length > 0) {
          try {
            const res = await fetch(`${API_BASE}/api/watchlist/prices`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ tickers: watchRows.map((r) => r.ticker) }),
            });
            const priceMap = res.ok ? await res.json() : {};
            setWatchlist(
              watchRows.map((r) => ({
                ticker: r.ticker,
                change_percent: priceMap[r.ticker]?.change_percent ?? null,
              }))
            );
          } catch {
            setWatchlist(watchRows.map((r) => ({ ticker: r.ticker, change_percent: null })));
          }
        } else {
          setWatchlist([]);
        }
      }
    } finally {
      setLoading(false);
    }
  }, [user?.id]);

  const fetchSectors = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/market/indices`);
      if (res.ok) {
        const data = await res.json();
        const sectorLikely = (data || []).filter(
          (idx) => idx.label && !["INR/USD"].includes(idx.label)
        );
        setSectors(sectorLikely.slice(0, 6));
      }
    } catch { /* optional */ }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);
  useEffect(() => { fetchSectors(); }, [fetchSectors]);

  const tabs = [
    { id: "holdings",  label: "Holdings",  count: holdings.length  },
    { id: "watchlist", label: "Watchlist", count: watchlist.length },
    { id: "indices",   label: "Indices",   count: sectors.length   },
  ];

  return (
    <aside
      data-tour="universe-rail"
      className="dash-universe-rail"
      style={{
        background: "var(--color-bg-card)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "12px",
        padding: "10px 6px 8px",
        height: "100%",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* HEADER + TABS */}
      <div style={{ padding: "0 6px", marginBottom: "8px" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "8px",
            marginBottom: "8px",
          }}
        >
          <h3
            style={{
              fontSize: "10px",
              fontWeight: 800,
              textTransform: "uppercase",
              letterSpacing: "0.10em",
              color: "var(--color-text-primary)",
              margin: 0,
              lineHeight: 1,
            }}
          >
            Your universe
          </h3>
          {demoMode && (
            <span
              style={{
                fontSize: "9px",
                fontWeight: 700,
                textTransform: "uppercase",
                padding: "1px 6px",
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

        {/* TABS */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            background: "var(--color-bg-secondary)",
            borderRadius: "7px",
            padding: "2px",
            gap: "2px",
          }}
        >
          {tabs.map((t) => {
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                style={{
                  padding: "4px 4px",
                  borderRadius: "5px",
                  border: "none",
                  background: active ? "var(--color-bg-card)" : "transparent",
                  color: active ? "var(--color-text-primary)" : "var(--color-text-muted)",
                  fontSize: "10px",
                  fontWeight: 700,
                  letterSpacing: "0.04em",
                  cursor: "pointer",
                  boxShadow: active ? "0 1px 0 rgba(255,255,255,0.04) inset" : "none",
                  transition: "background 0.15s, color 0.15s",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: "4px",
                  lineHeight: 1.2,
                }}
              >
                {t.label}
                {t.count > 0 && (
                  <span
                    style={{
                      fontSize: "9px",
                      fontWeight: 600,
                      padding: "0 4px",
                      borderRadius: "9999px",
                      background: active
                        ? "rgba(99,102,241,0.18)"
                        : "rgba(148,163,184,0.10)",
                      color: active
                        ? "var(--color-accent-secondary)"
                        : "var(--color-text-muted)",
                      lineHeight: 1.4,
                    }}
                  >
                    {t.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* BODY */}
      {loading ? (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            padding: "16px 12px",
            color: "var(--color-text-muted)",
            fontSize: "11px",
          }}
        >
          <Spinner size="sm" />
          Loading…
        </div>
      ) : (
        <div style={{ flex: 1, overflowY: "auto" }}>
          {tab === "holdings" && (
            <>
              {holdings.length === 0 ? (
                <EmptyHint text="Import your portfolio to track live P&L." />
              ) : (
                holdings.map((h) => (
                  <Row
                    key={h.ticker}
                    ticker={h.ticker}
                    change_percent={h.change_percent}
                    onClick={() => onNavigate?.("company", h.ticker)}
                  />
                ))
              )}
              {onOpenPortfolio && holdings.length > 0 && (
                <button
                  type="button"
                  onClick={onOpenPortfolio}
                  style={inlineLinkStyle}
                >
                  Manage portfolio →
                </button>
              )}
            </>
          )}

          {tab === "watchlist" && (
            <>
              {watchlist.length === 0 ? (
                <EmptyHint text="Add stocks via the Screener." />
              ) : (
                watchlist.map((w) => (
                  <Row
                    key={w.ticker}
                    ticker={w.ticker}
                    change_percent={w.change_percent}
                    onClick={() => onNavigate?.("company", w.ticker)}
                  />
                ))
              )}
              {onOpenWatchlist && (
                <button
                  type="button"
                  onClick={onOpenWatchlist}
                  style={inlineLinkStyle}
                >
                  Manage watchlist →
                </button>
              )}
            </>
          )}

          {tab === "indices" && (
            <>
              {sectors.length === 0 ? (
                <EmptyHint text="Index data unavailable right now." />
              ) : (
                sectors.map((s) => {
                  const pctMatch = String(s.change || "").match(/-?\d+\.?\d*/);
                  const pct = pctMatch ? parseFloat(pctMatch[0]) : null;
                  return (
                    <div
                      key={s.label}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        padding: "5px 10px",
                        fontSize: "11px",
                        lineHeight: 1.2,
                      }}
                    >
                      <span style={{ color: "var(--color-text-secondary)" }}>
                        {s.label}
                      </span>
                      <ChangeCell pct={pct} />
                    </div>
                  );
                })
              )}
            </>
          )}
        </div>
      )}

      {/* FOOTER — quick actions */}
      {(onOpenScreener || onOpenWatchlist) && (
        <div
          style={{
            marginTop: "6px",
            padding: "6px 6px 0",
            borderTop: "1px solid var(--border-subtle)",
            display: "flex",
            gap: "5px",
          }}
        >
          {onOpenScreener && (
            <button
              type="button"
              onClick={onOpenScreener}
              style={quickActionStyle}
            >
              <SearchIcon size={12} /> Find
            </button>
          )}
          {onOpenWatchlist && (
            <button
              type="button"
              onClick={onOpenWatchlist}
              style={quickActionStyle}
            >
              <TargetIcon size={12} /> Watch
            </button>
          )}
        </div>
      )}
    </aside>
  );
}

function EmptyHint({ text }) {
  return (
    <p
      style={{
        fontSize: "11px",
        color: "var(--color-text-muted)",
        padding: "14px 10px",
        fontStyle: "italic",
        lineHeight: 1.5,
      }}
    >
      {text}
    </p>
  );
}

const inlineLinkStyle = {
  width: "100%",
  marginTop: "6px",
  padding: "5px 10px",
  borderRadius: "5px",
  border: "1px dashed var(--border-subtle)",
  background: "transparent",
  color: "var(--color-accent-secondary)",
  fontSize: "10.5px",
  fontWeight: 700,
  cursor: "pointer",
  letterSpacing: "0.02em",
  lineHeight: 1.4,
};

const quickActionStyle = {
  flex: 1,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gap: "5px",
  padding: "6px 8px",
  borderRadius: "var(--radius-pill)",
  border: "1px solid var(--border-subtle)",
  background: "var(--color-bg-card)",
  color: "var(--color-text-secondary)",
  fontSize: "10.5px",
  fontWeight: 600,
  cursor: "pointer",
  letterSpacing: "0.01em",
  lineHeight: 1.4,
};
