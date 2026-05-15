"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { DashboardIcon, SettingsIcon, TargetIcon } from "./Icons";

/**
 * Sidebar — "editorial terminal" redesign.
 * Solid surface, hairline borders, inline SVG icons (no emoji), a flat
 * monogram mark (no gradient block). Active state is a quiet accent: a
 * 2px left rule + faint tinted fill, not a glow.
 */
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

  // Hub-and-drawer model: dashboard is the main view. Track record is a
  // first-class internal tab now (was previously a separate Next.js route);
  // page.js still renders the standalone /accuracy page for public sharing.
  const navItems = [
    { id: "dashboard", label: "Dashboard",    Icon: DashboardIcon },
    { id: "accuracy",  label: "Track record", Icon: TargetIcon },
    { id: "settings",  label: "Settings",     Icon: SettingsIcon },
  ];

  // No off-app routes today — kept for future use.
  const externalLinks = [];

  // ---- MOBILE: bottom navigation bar --------------------------------------
  if (isMobile) {
    return (
      <nav
        className="sidebar-mobile"
        style={{
          position: "fixed",
          bottom: 0,
          left: 0,
          right: 0,
          height: "60px",
          background: "var(--color-bg-secondary)",
          borderTop: "1px solid var(--border-subtle)",
          zIndex: 50,
          justifyContent: "space-around",
          alignItems: "center",
          paddingBottom: "env(safe-area-inset-bottom, 0px)",
        }}
      >
        {navItems.map((item) => {
          const active = activeNav === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onNavChange?.(item.id)}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: "3px",
                padding: "6px 0",
                border: "none",
                background: "transparent",
                cursor: "pointer",
                minWidth: "56px",
                color: active ? "var(--color-text-primary)" : "var(--color-text-muted)",
                transition: "color 0.15s",
              }}
            >
              <item.Icon size={19} />
              <span style={{ fontSize: "9.5px", fontWeight: 600, letterSpacing: "0.01em" }}>
                {item.label}
              </span>
            </button>
          );
        })}
        {externalLinks.map((item) => (
          <Link
            key={item.id}
            href={item.href}
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: "3px",
              padding: "6px 0",
              minWidth: "56px",
              color: "var(--color-text-muted)",
              textDecoration: "none",
            }}
          >
            <item.Icon size={19} />
            <span style={{ fontSize: "9.5px", fontWeight: 600, letterSpacing: "0.01em" }}>
              {item.label}
            </span>
          </Link>
        ))}
      </nav>
    );
  }

  // ---- TABLET: icon-only narrow rail / DESKTOP: full rail -----------------
  const sidebarWidth = isTablet ? "64px" : "240px";

  const NavRow = ({ item, active, asLink }) => {
    const inner = (
      <>
        <span
          style={{
            display: "flex",
            color: active ? "var(--color-accent-primary)" : "var(--color-text-muted)",
            transition: "color 0.15s",
          }}
        >
          <item.Icon size={18} />
        </span>
        {!isTablet && <span>{item.label}</span>}
      </>
    );
    const sharedStyle = {
      width: "100%",
      display: "flex",
      alignItems: "center",
      gap: "11px",
      padding: isTablet ? "10px 0" : "9px 12px",
      borderRadius: "var(--radius-control)",
      fontSize: "13px",
      fontWeight: active ? 600 : 500,
      border: "none",
      cursor: "pointer",
      transition: "background 0.15s, color 0.15s",
      justifyContent: isTablet ? "center" : "flex-start",
      background: active ? "rgba(99,102,241,0.10)" : "transparent",
      color: active ? "var(--color-text-primary)" : "var(--color-text-secondary)",
      textDecoration: "none",
      position: "relative",
    };
    const onHover = (e, on) => {
      if (active) return;
      e.currentTarget.style.background = on ? "rgba(255,255,255,0.04)" : "transparent";
    };
    if (asLink) {
      return (
        <Link
          href={item.href}
          title={isTablet ? item.label : undefined}
          style={sharedStyle}
          onMouseEnter={(e) => onHover(e, true)}
          onMouseLeave={(e) => onHover(e, false)}
        >
          {inner}
        </Link>
      );
    }
    return (
      <button
        onClick={() => onNavChange?.(item.id)}
        title={isTablet ? item.label : undefined}
        style={sharedStyle}
        onMouseEnter={(e) => onHover(e, true)}
        onMouseLeave={(e) => onHover(e, false)}
      >
        {/* Active rule — 2px accent bar on the left edge */}
        {active && !isTablet && (
          <span
            style={{
              position: "absolute",
              left: 0,
              top: "18%",
              bottom: "18%",
              width: "2px",
              borderRadius: "2px",
              background: "var(--color-accent-primary)",
            }}
          />
        )}
        {inner}
      </button>
    );
  };

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
        transition: "width 0.18s ease",
        overflow: "hidden",
      }}
    >
      {/* Brand — flat monogram, no gradient block */}
      <div
        style={{
          padding: isTablet ? "20px 0" : "22px 20px",
          display: "flex",
          alignItems: "center",
          gap: "11px",
          justifyContent: isTablet ? "center" : "flex-start",
          borderBottom: "1px solid var(--border-subtle)",
        }}
      >
        <div
          style={{
            width: "30px",
            height: "30px",
            borderRadius: "7px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--color-text-primary)",
            fontWeight: 700,
            fontSize: "15px",
            flexShrink: 0,
            background: "var(--color-bg-card-hover)",
            border: "1px solid var(--border-strong)",
            letterSpacing: "-0.03em",
          }}
        >
          F
        </div>
        {!isTablet && (
          <div style={{ lineHeight: 1.25 }}>
            <h1
              style={{
                fontSize: "14px",
                fontWeight: 700,
                color: "var(--color-text-primary)",
                letterSpacing: "-0.02em",
              }}
            >
              FinContext
            </h1>
            <p style={{ fontSize: "10.5px", color: "var(--color-text-muted)", letterSpacing: "0.01em" }}>
              Market intelligence
            </p>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav style={{ flex: 1, padding: isTablet ? "12px 8px" : "14px 12px" }}>
        {!isTablet && (
          <div
            style={{
              fontSize: "10px",
              fontWeight: 600,
              color: "var(--color-text-muted)",
              textTransform: "uppercase",
              letterSpacing: "0.09em",
              padding: "0 12px 8px",
            }}
          >
            Navigate
          </div>
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
          {navItems.map((item) => (
            <NavRow key={item.id} item={item} active={activeNav === item.id} />
          ))}
          {externalLinks.map((item) => (
            <NavRow key={item.id} item={item} active={false} asLink />
          ))}
        </div>
      </nav>

      {/* Live indicator — quiet, no glow */}
      <div style={{ padding: isTablet ? "14px 8px" : "16px 20px", borderTop: "1px solid var(--border-subtle)" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            justifyContent: isTablet ? "center" : "flex-start",
          }}
        >
          <span
            className="pulse-dot"
            style={{
              width: "6px",
              height: "6px",
              borderRadius: "50%",
              background: "var(--color-accent-green)",
              display: "inline-block",
              flexShrink: 0,
            }}
          />
          {!isTablet && (
            <span style={{ fontSize: "11px", fontWeight: 500, color: "var(--color-text-secondary)" }}>
              Market open
            </span>
          )}
        </div>
      </div>
    </aside>
  );
}
