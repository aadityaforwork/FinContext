"use client";

import Link from "next/link";

/**
 * LandingFooter — Ft2 inline single line. No column grid, no social row,
 * no "Resources" or "Legal" headers standing in for links this page
 * doesn't have. One hairline rule, one line.
 */
export default function LandingFooter() {
  return (
    <footer
      style={{
        borderTop: "1px solid var(--border-subtle)",
        padding: "var(--space-lg) clamp(1rem, 4vw, 2.5rem)",
        marginTop: "var(--space-xl)",
      }}
    >
      <div
        style={{
          maxWidth: "1180px",
          margin: "0 auto",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "var(--space-md)",
          flexWrap: "wrap",
          fontSize: "12.5px",
          color: "var(--color-text-muted)",
        }}
      >
        <span>© 2026 FinContext</span>
        <div style={{ display: "flex", gap: "var(--space-lg)" }}>
          <Link href="/login" style={{ color: "var(--color-text-muted)", whiteSpace: "nowrap" }}>
            Sign in
          </Link>
          <Link href="/accuracy" style={{ color: "var(--color-text-muted)", whiteSpace: "nowrap" }}>
            Track record
          </Link>
        </div>
      </div>
    </footer>
  );
}
