"use client";

import Link from "next/link";

/**
 * LandingNav — N9 "edge-aligned minimal": wordmark hard-left, one real
 * action hard-right, empty space between. No link row — the page below
 * only has two destinations (sign in / sign up), so a filled 4–5-link bar
 * would be padding, not navigation. Reuses the flat-monogram wordmark
 * treatment from AuthCard.jsx so the mark reads the same on every route.
 */
export default function LandingNav() {
  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "var(--space-md)",
        padding: "var(--space-md) clamp(1rem, 4vw, 2.5rem)",
        borderBottom: "1px solid var(--border-subtle)",
      }}
    >
      <Link
        href="/"
        style={{
          display: "flex",
          alignItems: "center",
          gap: "10px",
          textDecoration: "none",
        }}
      >
        <span
          style={{
            width: "26px",
            height: "26px",
            borderRadius: "7px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--color-text-primary)",
            fontWeight: 700,
            fontSize: "13px",
            flexShrink: 0,
            background: "var(--color-bg-card-hover)",
            border: "1px solid var(--border-strong)",
            letterSpacing: "-0.03em",
          }}
        >
          F
        </span>
        <span
          style={{
            fontSize: "14px",
            fontWeight: 700,
            color: "var(--color-text-primary)",
            letterSpacing: "-0.02em",
          }}
        >
          FinContext
        </span>
      </Link>

      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-lg)" }}>
        <Link
          href="/login"
          style={{
            fontSize: "13px",
            fontWeight: 600,
            color: "var(--color-text-secondary)",
            textDecoration: "none",
            whiteSpace: "nowrap",
          }}
        >
          Sign in
        </Link>
        <Link
          href="/signup"
          style={{
            fontSize: "13px",
            fontWeight: 600,
            color: "#fff",
            background: "var(--color-accent-primary)",
            border: "1px solid var(--color-accent-primary)",
            borderRadius: "var(--radius-control, 8px)",
            padding: "8px 14px",
            textDecoration: "none",
            whiteSpace: "nowrap",
            transition: "filter var(--dur-short) var(--ease-out)",
          }}
        >
          Start free
        </Link>
      </div>
    </header>
  );
}
