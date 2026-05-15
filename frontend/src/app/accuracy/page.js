"use client";

import Link from "next/link";
import AccuracyView from "../components/AccuracyView";

/**
 * /accuracy — public Track Record page.
 *
 * Thin wrapper that renders <AccuracyView embedded={false} /> with a top
 * nav strip and the standalone "Does it actually work?" framing. Logged-in
 * users reach the same content via the dashboard sidebar tab; this route
 * exists for landing-page traffic and unauthenticated sharing.
 */
export default function AccuracyPage() {
  return (
    <div style={{
      minHeight: "100vh",
      background: "var(--color-bg-primary, #0a0b14)",
      color: "var(--color-text-primary)",
    }}>
      <header style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "18px 28px", borderBottom: "1px solid var(--border-subtle)",
      }}>
        <Link href="/" style={{
          fontSize: "13px", fontWeight: 800, color: "var(--color-text-primary)",
          textDecoration: "none", letterSpacing: "-0.01em",
        }}>
          ← FinContext
        </Link>
        <div style={{
          fontSize: "10px", fontWeight: 700, color: "var(--color-text-muted)",
          textTransform: "uppercase", letterSpacing: "0.08em",
        }}>
          Track record · Public
        </div>
      </header>

      <AccuracyView embedded={false} />
    </div>
  );
}
