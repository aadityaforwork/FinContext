"use client";

import { useState, useRef, useEffect } from "react";

export default function DashboardHeader({ onSearch, user, onLogout }) {
  const today = new Date().toLocaleDateString("en-IN", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    function onDocClick(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setMenuOpen(false);
      }
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

  return (
    <header className="header-responsive">
      <div>
        <h2 style={{ fontSize: "24px", fontWeight: 700, color: "var(--color-text-primary)" }}>
          Dashboard
        </h2>
        <p style={{ fontSize: "13px", marginTop: "2px", color: "var(--color-text-muted)" }}>
          {today} • NSE / BSE
        </p>
      </div>

      <div className="header-actions">
        <div className="header-search" style={{ position: "relative" }}>
          <input
            type="text"
            placeholder="Search tickers..."
            onKeyDown={handleKeyDown}
            style={{
              width: "100%",
              padding: "8px 16px 8px 38px",
              borderRadius: "12px",
              fontSize: "13px",
              border: "1px solid var(--border-subtle)",
              outline: "none",
              background: "var(--color-bg-card)",
              color: "var(--color-text-primary)",
            }}
          />
          <svg
            style={{
              position: "absolute",
              left: "12px",
              top: "50%",
              transform: "translateY(-50%)",
              width: "16px",
              height: "16px",
              color: "var(--color-text-muted)",
            }}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
        </div>

        <button
          style={{
            position: "relative",
            padding: "8px",
            borderRadius: "12px",
            background: "var(--color-bg-card)",
            border: "none",
            cursor: "pointer",
          }}
        >
          <svg
            style={{ width: "20px", height: "20px", color: "var(--color-text-secondary)" }}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
            />
          </svg>
          <span
            style={{
              position: "absolute",
              top: "-2px",
              right: "-2px",
              width: "10px",
              height: "10px",
              borderRadius: "50%",
              background: "var(--color-accent-red)",
            }}
          />
        </button>

        {/* User menu */}
        <div ref={menuRef} style={{ position: "relative" }}>
          <button
            type="button"
            onClick={() => setMenuOpen((v) => !v)}
            title={displayName}
            style={{
              width: "36px",
              height: "36px",
              borderRadius: "50%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: "14px",
              fontWeight: 700,
              color: "white",
              border: "none",
              cursor: "pointer",
              overflow: "hidden",
              padding: 0,
              background:
                "linear-gradient(135deg, var(--color-accent-primary), var(--color-accent-cyan))",
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
                top: "44px",
                minWidth: "220px",
                background: "var(--color-bg-card)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "12px",
                boxShadow: "var(--shadow-card)",
                padding: "8px",
                zIndex: 100,
              }}
            >
              <div style={{ padding: "8px 10px", borderBottom: "1px solid var(--border-subtle)", marginBottom: "6px" }}>
                <p style={{ fontSize: "13px", fontWeight: 600, color: "var(--color-text-primary)" }}>
                  {user?.name || "Signed in"}
                </p>
                <p style={{ fontSize: "12px", color: "var(--color-text-muted)", wordBreak: "break-all" }}>
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
                  padding: "8px 10px",
                  borderRadius: "8px",
                  border: "none",
                  background: "transparent",
                  color: "var(--color-text-primary)",
                  cursor: "pointer",
                  fontSize: "13px",
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "var(--color-bg-card-hover)")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
              >
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
