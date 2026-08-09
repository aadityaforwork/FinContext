"use client";

import Link from "next/link";

/**
 * TrackRecord — the trust section. Deliberately carries no number of its
 * own: the real, live accuracy figure lives on /accuracy and changes as
 * more calls get graded. Restating a snapshot here would go stale and,
 * per Hallmark's honest-copy rule, an invented or frozen stat is worse
 * than none — so this section links out instead of quoting one.
 */
export default function TrackRecord() {
  return (
    <section
      style={{
        padding: "var(--space-2xl) clamp(1rem, 4vw, 2.5rem)",
        maxWidth: "1180px",
        margin: "0 auto",
        borderTop: "1px solid var(--border-subtle)",
      }}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "7fr 5fr",
          gap: "var(--space-2xl)",
          alignItems: "start",
        }}
        className="landing-split"
      >
        <div>
          <h2
            style={{
              fontFamily: "var(--font-serif)",
              fontSize: "clamp(1.875rem, 2.5vw + 1rem, 2.75rem)",
              fontWeight: 700,
              lineHeight: 1.1,
              letterSpacing: "-0.01em",
              color: "var(--color-text-primary)",
              margin: "0 0 var(--space-md)",
            }}
          >
            A public scorecard, not a promise
          </h2>
          <p
            style={{
              fontSize: "15px",
              lineHeight: 1.65,
              color: "var(--color-text-secondary)",
              maxWidth: "58ch",
              margin: "0 0 var(--space-lg)",
            }}
          >
            We don&rsquo;t ask you to take our accuracy on faith. Every
            directional call FinContext makes is logged the moment it&rsquo;s
            made and checked automatically against real closing prices — 1
            day, 5 days, and 20 days out. Nothing is excluded after the fact.
          </p>
          <Link
            href="/accuracy"
            style={{
              fontSize: "14px",
              fontWeight: 600,
              color: "var(--color-accent-secondary)",
              textDecoration: "underline",
              textUnderlineOffset: "3px",
              whiteSpace: "nowrap",
              display: "inline-block",
            }}
          >
            See the full record →
          </Link>
        </div>

        <div
          style={{
            background: "var(--color-bg-card)",
            border: "1px solid var(--border-subtle)",
            borderRadius: "var(--radius-card)",
            padding: "var(--space-lg)",
          }}
        >
          <p
            style={{
              fontSize: "10px",
              fontWeight: 700,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "var(--color-text-muted)",
              margin: "0 0 var(--space-sm)",
            }}
          >
            Graded automatically
          </p>
          <p
            style={{
              fontSize: "13.5px",
              lineHeight: 1.6,
              color: "var(--color-text-secondary)",
              margin: 0,
            }}
          >
            1‑day · 5‑day · 20‑day windows, scored against closing prices —
            not our own read of the outcome.
          </p>
        </div>
      </div>
    </section>
  );
}
