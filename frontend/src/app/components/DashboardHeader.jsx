"use client";

import { useState, useRef, useEffect } from "react";
import { SearchIcon, BellIcon, LogoutIcon } from "./Icons";
import { API_BASE } from "../lib/api";

/**
 * DashboardHeader — "editorial terminal" redesign.
 * Hairline-bordered controls, SVG icons (no inline path soup), a flat
 * monogram avatar (no gradient disc). Title scaled down from the loud 24px.
 *
 * Props:
 *   onSearch        — routes the typed ticker to the screener (existing).
 *   onCheckTicker   — opens the Pre-Trade Check modal for a ticker. This is
 *                     the muscle-memory "before you click buy" affordance —
 *                     a primary header pill next to the search box.
 */
export default function DashboardHeader({ onSearch, onCheckTicker, user, onLogout }) {
  const today = new Date().toLocaleDateString("en-IN", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  const [menuOpen, setMenuOpen] = useState(false);
  const [bellOpen, setBellOpen] = useState(false);
  const [checkOpen, setCheckOpen] = useState(false);
  const [checkQuery, setCheckQuery] = useState("");
  const [checkResults, setCheckResults] = useState([]);
  const menuRef = useRef(null);
  const bellRef = useRef(null);
  const checkRef = useRef(null);
  const checkInputRef = useRef(null);

  useEffect(() => {
    function onDocClick(e) {
      if (menuRef.current  && !menuRef.current.contains(e.target))  setMenuOpen(false);
      if (bellRef.current  && !bellRef.current.contains(e.target))  setBellOpen(false);
      if (checkRef.current && !checkRef.current.contains(e.target)) setCheckOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  // Focus the input when the pre-trade-check popover opens so the user can
  // start typing immediately — half the point of this affordance is speed.
  useEffect(() => {
    if (checkOpen) {
      setTimeout(() => checkInputRef.current?.focus(), 30);
    } else {
      setCheckQuery("");
      setCheckResults([]);
    }
  }, [checkOpen]);

  // Autocomplete the same way AnalysisView does — /api/stocks/search.
  useEffect(() => {
    const q = checkQuery.trim();
    if (q.length < 2) { setCheckResults([]); return; }
    let cancelled = false;
    fetch(`${API_BASE}/api/stocks/search?q=${encodeURIComponent(q)}&limit=6`)
      .then((r) => r.ok ? r.json() : [])
      .then((rows) => { if (!cancelled) setCheckResults(rows || []); })
      .catch(() => { if (!cancelled) setCheckResults([]); });
    return () => { cancelled = true; };
  }, [checkQuery]);

  const launchCheck = (ticker) => {
    if (!ticker) return;
    setCheckOpen(false);
    onCheckTicker?.(ticker.toUpperCase());
  };

  const handleCheckKey = (e) => {
    if (e.key === "Escape") { setCheckOpen(false); }
    else if (e.key === "Enter") {
      // Prefer the highlighted result; otherwise treat raw input as a ticker.
      const t = checkResults[0]?.ticker || checkQuery.trim();
      if (t) launchCheck(t);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && e.target.value.trim()) {
      onSearch?.(e.target.value.trim());
    }
  };

  const initial =
    (user?.name && user.name.trim()[0]) ||
    (user?.email && user.email[0]) ||
    "A";
  const displayName = user?.name || user?.email || "";

  // Shared icon-button styling — hairline border, solid surface, no glow.
  const iconBtn = {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width: "34px",
    height: "34px",
    borderRadius: "var(--radius-control)",
    background: "var(--color-bg-card)",
    border: "1px solid var(--border-subtle)",
    color: "var(--color-text-secondary)",
    cursor: "pointer",
    transition: "border-color 0.15s, color 0.15s",
  };

  return (
    <header className="header-responsive">
      <div>
        <h2
          style={{
            fontSize: "19px",
            fontWeight: 700,
            color: "var(--color-text-primary)",
            letterSpacing: "-0.02em",
          }}
        >
          Dashboard
        </h2>
        <p
          style={{
            fontSize: "12px",
            marginTop: "3px",
            color: "var(--color-text-muted)",
            letterSpacing: "0.005em",
          }}
        >
          {today} &nbsp;·&nbsp; NSE / BSE
        </p>
      </div>

      <div className="header-actions">
        {/* Search */}
        <div className="header-search" style={{ position: "relative" }}>
          <input
            type="text"
            placeholder="Search tickers…"
            onKeyDown={handleKeyDown}
            style={{
              width: "100%",
              padding: "8px 14px 8px 36px",
              borderRadius: "var(--radius-control)",
              fontSize: "13px",
              border: "1px solid var(--border-subtle)",
              outline: "none",
              background: "var(--color-bg-card)",
              color: "var(--color-text-primary)",
              transition: "border-color 0.15s",
            }}
            onFocus={(e) => (e.currentTarget.style.borderColor = "var(--border-active)")}
            onBlur={(e) => (e.currentTarget.style.borderColor = "var(--border-subtle)")}
          />
          <span
            style={{
              position: "absolute",
              left: "11px",
              top: "50%",
              transform: "translateY(-50%)",
              display: "flex",
              color: "var(--color-text-muted)",
              pointerEvents: "none",
            }}
          >
            <SearchIcon size={15} />
          </span>
        </div>

        {/* Pre-trade check — the muscle-memory affordance. Primary, indigo. */}
        <div ref={checkRef} style={{ position: "relative" }}>
          <button
            type="button"
            onClick={() => setCheckOpen((v) => !v)}
            aria-expanded={checkOpen}
            aria-label="Pre-trade check — run a quick scorecard on any ticker before you trade"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              padding: "7px 12px",
              borderRadius: "var(--radius-control)",
              border: "1px solid var(--color-accent-primary)",
              background: checkOpen ? "var(--color-accent-primary)" : "transparent",
              color: checkOpen ? "#fff" : "var(--color-accent-primary)",
              fontSize: "11px",
              fontWeight: 700,
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              fontFamily: "var(--font-mono)",
              cursor: "pointer",
              whiteSpace: "nowrap",
              transition: "background 0.15s, color 0.15s",
            }}
          >
            <span aria-hidden style={{ fontSize: "13px", lineHeight: 1 }}>✓</span>
            Pre-trade check
          </button>

          {checkOpen && (
            <div
              role="dialog"
              aria-label="Pre-trade check"
              style={{
                position: "absolute",
                right: 0,
                top: "44px",
                width: "min(360px, 90vw)",
                background: "var(--color-bg-card)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-card)",
                boxShadow: "var(--shadow-pop)",
                padding: "12px",
                zIndex: 100,
              }}
            >
              <div
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "9.5px",
                  fontWeight: 700,
                  letterSpacing: "0.18em",
                  textTransform: "uppercase",
                  color: "var(--color-text-muted)",
                  marginBottom: "8px",
                }}
              >
                Check a ticker before you trade
              </div>
              <input
                ref={checkInputRef}
                type="text"
                placeholder="e.g. RELIANCE, INFY, TCS"
                value={checkQuery}
                onChange={(e) => setCheckQuery(e.target.value)}
                onKeyDown={handleCheckKey}
                style={{
                  width: "100%",
                  padding: "9px 12px",
                  borderRadius: "var(--radius-control)",
                  fontSize: "13px",
                  border: "1px solid var(--border-subtle)",
                  outline: "none",
                  background: "var(--color-bg-primary)",
                  color: "var(--color-text-primary)",
                  fontFamily: "var(--font-mono)",
                  letterSpacing: "0.01em",
                }}
                onFocus={(e) => (e.currentTarget.style.borderColor = "var(--border-active)")}
                onBlur={(e)  => (e.currentTarget.style.borderColor = "var(--border-subtle)")}
              />

              {checkResults.length > 0 && (
                <ul
                  style={{
                    listStyle: "none",
                    padding: 0,
                    margin: "8px 0 0",
                    border: "1px solid var(--border-subtle)",
                    borderRadius: "var(--radius-control)",
                    overflow: "hidden",
                  }}
                >
                  {checkResults.map((s, i) => (
                    <li key={s.ticker}>
                      <button
                        type="button"
                        onClick={() => launchCheck(s.ticker)}
                        style={{
                          width: "100%",
                          textAlign: "left",
                          padding: "9px 12px",
                          background: "transparent",
                          border: "none",
                          borderBottom: i === checkResults.length - 1 ? "none" : "1px solid var(--border-subtle)",
                          cursor: "pointer",
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          gap: "10px",
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = "var(--color-bg-card-hover)")}
                        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                      >
                        <span style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                          <span style={{ fontFamily: "var(--font-mono)", fontSize: "12.5px", fontWeight: 700, color: "var(--color-text-primary)" }}>
                            {s.ticker}
                          </span>
                          <span style={{ fontSize: "11px", color: "var(--color-text-muted)" }}>
                            {s.name}
                          </span>
                        </span>
                        <span
                          style={{
                            padding: "2px 7px",
                            fontSize: "9.5px",
                            fontWeight: 700,
                            letterSpacing: "0.1em",
                            textTransform: "uppercase",
                            color: "var(--color-text-muted)",
                            border: "1px solid var(--border-subtle)",
                            borderRadius: "4px",
                            fontFamily: "var(--font-mono)",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {s.sector}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              <p style={{
                fontSize: "10.5px",
                color: "var(--color-text-muted)",
                marginTop: "10px",
                fontStyle: "italic",
                lineHeight: 1.5,
                fontFamily: "var(--font-serif)",
              }}>
                Six grounded checks — none of them a recommendation. Press Enter or click a result.
              </p>
            </div>
          )}
        </div>

        {/* Notifications */}
        <div ref={bellRef} style={{ position: "relative" }}>
          <button
            type="button"
            onClick={() => setBellOpen((v) => !v)}
            aria-label="Notifications"
            aria-expanded={bellOpen}
            style={iconBtn}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = "var(--border-strong)";
              e.currentTarget.style.color = "var(--color-text-primary)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = "var(--border-subtle)";
              e.currentTarget.style.color = "var(--color-text-secondary)";
            }}
          >
            <BellIcon size={17} />
          </button>

          {bellOpen && (
            <div
              role="dialog"
              style={{
                position: "absolute",
                right: 0,
                top: "42px",
                minWidth: "262px",
                background: "var(--color-bg-card)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-card)",
                boxShadow: "var(--shadow-pop)",
                padding: "14px",
                zIndex: 100,
              }}
            >
              <p style={{ fontSize: "12.5px", fontWeight: 700, color: "var(--color-text-primary)" }}>
                Notifications
              </p>
              <p
                style={{
                  fontSize: "11.5px",
                  color: "var(--color-text-muted)",
                  marginTop: "6px",
                  lineHeight: 1.5,
                }}
              >
                Real-time alerts on portfolio events, news mentions, and risk shifts are coming soon.
              </p>
            </div>
          )}
        </div>

        {/* User menu — flat monogram avatar */}
        <div ref={menuRef} style={{ position: "relative" }}>
          <button
            type="button"
            onClick={() => setMenuOpen((v) => !v)}
            title={displayName}
            style={{
              width: "34px",
              height: "34px",
              borderRadius: "var(--radius-control)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: "13px",
              fontWeight: 700,
              color: "var(--color-text-primary)",
              border: "1px solid var(--border-strong)",
              cursor: "pointer",
              overflow: "hidden",
              padding: 0,
              background: "var(--color-bg-card-hover)",
            }}
          >
            {user?.avatar_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={user.avatar_url}
                alt={displayName}
                style={{ width: "100%", height: "100%", objectFit: "cover" }}
                referrerPolicy="no-referrer"
              />
            ) : (
              <span style={{ textTransform: "uppercase" }}>{initial}</span>
            )}
          </button>

          {menuOpen && (
            <div
              style={{
                position: "absolute",
                right: 0,
                top: "42px",
                minWidth: "220px",
                background: "var(--color-bg-card)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-card)",
                boxShadow: "var(--shadow-pop)",
                padding: "6px",
                zIndex: 100,
              }}
            >
              <div
                style={{
                  padding: "8px 10px",
                  borderBottom: "1px solid var(--border-subtle)",
                  marginBottom: "4px",
                }}
              >
                <p style={{ fontSize: "12.5px", fontWeight: 600, color: "var(--color-text-primary)" }}>
                  {user?.name || "Signed in"}
                </p>
                <p style={{ fontSize: "11.5px", color: "var(--color-text-muted)", wordBreak: "break-all" }}>
                  {user?.email}
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  onLogout?.();
                }}
                style={{
                  width: "100%",
                  textAlign: "left",
                  display: "flex",
                  alignItems: "center",
                  gap: "9px",
                  padding: "8px 10px",
                  borderRadius: "var(--radius-control)",
                  border: "none",
                  background: "transparent",
                  color: "var(--color-text-secondary)",
                  cursor: "pointer",
                  fontSize: "12.5px",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = "var(--color-bg-card-hover)";
                  e.currentTarget.style.color = "var(--color-text-primary)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "transparent";
                  e.currentTarget.style.color = "var(--color-text-secondary)";
                }}
              >
                <LogoutIcon size={15} />
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
