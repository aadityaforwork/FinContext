"use client";

import { useState, useRef, useEffect } from "react";
import { SearchIcon, BellIcon, LogoutIcon } from "./Icons";

/**
 * DashboardHeader — "editorial terminal" redesign.
 * Hairline-bordered controls, SVG icons (no inline path soup), a flat
 * monogram avatar (no gradient disc). Title scaled down from the loud 24px.
 */
export default function DashboardHeader({ onSearch, user, onLogout }) {
  const today = new Date().toLocaleDateString("en-IN", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  const [menuOpen, setMenuOpen] = useState(false);
  const [bellOpen, setBellOpen] = useState(false);
  const menuRef = useRef(null);
  const bellRef = useRef(null);

  useEffect(() => {
    function onDocClick(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false);
      if (bellRef.current && !bellRef.current.contains(e.target)) setBellOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

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
