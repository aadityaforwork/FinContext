"use client";

import { useState, useEffect } from "react";

export default function Sidebar({ activeNav, onNavChange }) {
  const [isMobile, setIsMobile] = useState(false);
  const [isTablet, setIsTablet] = useState(false);

  useEffect(() => {
    const check = () => {
      setIsMobile(window.innerWidth <= 768);
      setIsTablet(window.innerWidth > 768 && window.innerWidth <= 1024);
    };
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  const navItems = [
    { id: "dashboard", label: "Dashboard", icon: "📊" },
    { id: "portfolio", label: "Portfolio", icon: "💼" },
    { id: "analysis", label: "Analysis", icon: "🧠" },
    { id: "company", label: "Company", icon: "🏢" },
    { id: "watchlist", label: "Watchlist", icon: "⭐" },
    { id: "screener", label: "Screener", icon: "🔍" },
  ];

  // ---- MOBILE: Bottom Navigation Bar ----
  if (isMobile) {
    return (
      <nav
        className="sidebar-mobile"
        style={{
          position: "fixed",
          bottom: 0,
          left: 0,
          right: 0,
          height: "64px",
          background: "var(--color-bg-secondary)",
          borderTop: "1px solid var(--border-subtle)",
          zIndex: 50,
          justifyContent: "space-around",
          alignItems: "center",
          paddingBottom: "env(safe-area-inset-bottom, 0px)",
        }}
      >
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => onNavChange?.(item.id)}
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: "2px",
              padding: "6px 0",
              border: "none",
              background: "transparent",
              cursor: "pointer",
              minWidth: "48px",
              color: activeNav === item.id ? "var(--color-accent-secondary)" : "var(--color-text-muted)",
              transition: "color 0.2s",
            }}
          >
            <span style={{ fontSize: "20px" }}>{item.icon}</span>
            <span style={{ fontSize: "9px", fontWeight: 600, letterSpacing: "0.02em" }}>{item.label}</span>
          </button>
        ))}
      </nav>
    );
  }

  // ---- TABLET: Icon-only narrow sidebar ----
  const sidebarWidth = isTablet ? "60px" : "240px";

  return (
    <aside
      className="sidebar-desktop"
      style={{
        width: sidebarWidth,
        minWidth: sidebarWidth,
        height: "100vh",
        position: "fixed",
        left: 0,
        top: 0,
        flexDirection: "column",
        background: "var(--color-bg-secondary)",
        borderRight: "1px solid var(--border-subtle)",
        zIndex: 50,
        transition: "width 0.2s ease",
        overflow: "hidden",
      }}
    >
      {/* Brand */}
      <div style={{ padding: isTablet ? "16px 10px" : "24px 20px", display: "flex", alignItems: "center", gap: "12px", justifyContent: isTablet ? "center" : "flex-start" }}>
        <div
          style={{
            width: isTablet ? "36px" : "40px",
            height: isTablet ? "36px" : "40px",
            borderRadius: "12px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "white",
            fontWeight: 700,
            fontSize: isTablet ? "16px" : "18px",
            flexShrink: 0,
            background: "linear-gradient(135deg, var(--color-accent-primary), var(--color-accent-cyan))",
          }}
        >
          F
        </div>
        {!isTablet && (
          <div>
            <h1 style={{ fontSize: "18px", fontWeight: 700, color: "var(--color-text-primary)" }}>
              FinContext
            </h1>
            <p style={{ fontSize: "12px", color: "var(--color-text-muted)" }}>
              Market Intelligence
            </p>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav style={{ flex: 1, padding: isTablet ? "0 6px" : "0 12px", marginTop: "16px" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => onNavChange?.(item.id)}
              title={isTablet ? item.label : undefined}
              style={{
                width: "100%",
                display: "flex",
                alignItems: "center",
                gap: "12px",
                padding: isTablet ? "10px 0" : "10px 14px",
                borderRadius: "12px",
                fontSize: "14px",
                fontWeight: 500,
                border: "none",
                cursor: "pointer",
                transition: "all 0.2s",
                justifyContent: isTablet ? "center" : "flex-start",
                background: activeNav === item.id ? "rgba(99, 102, 241, 0.15)" : "transparent",
                color: activeNav === item.id ? "var(--color-accent-secondary)" : "var(--color-text-secondary)",
                borderLeft: isTablet ? "none" : (activeNav === item.id ? "3px solid var(--color-accent-primary)" : "3px solid transparent"),
              }}
            >
              <span style={{ fontSize: "18px" }}>{item.icon}</span>
              {!isTablet && <span>{item.label}</span>}
            </button>
          ))}
        </div>
      </nav>

      {/* Live Indicator */}
      <div style={{ padding: isTablet ? "12px 6px" : "20px" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            padding: isTablet ? "8px 0" : "8px 12px",
            borderRadius: "8px",
            background: "rgba(16, 185, 129, 0.1)",
            justifyContent: isTablet ? "center" : "flex-start",
          }}
        >
          <span
            className="pulse-dot"
            style={{
              width: "8px",
              height: "8px",
              borderRadius: "50%",
              background: "var(--color-accent-green)",
              display: "inline-block",
            }}
          />
          {!isTablet && (
            <span style={{ fontSize: "12px", fontWeight: 500, color: "var(--color-accent-green)" }}>
              Market Open
            </span>
          )}
        </div>
      </div>
    </aside>
  );
}
