"use client";

import Link from "next/link";

/**
 * CTASection — one button, not two (repetition of two CTAs in one strip
 * reads as indecision). Asymmetric band, not centred: heading left,
 * action right, matching the rest of the page's left-biased rhythm.
 */
export default function CTASection() {
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
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "var(--space-lg)",
          flexWrap: "wrap",
        }}
      >
        <h2
          style={{
            fontFamily: "var(--font-serif)",
            fontSize: "clamp(1.625rem, 2vw + 1rem, 2.25rem)",
            fontWeight: 700,
            lineHeight: 1.15,
            letterSpacing: "-0.01em",
            color: "var(--color-text-primary)",
            margin: 0,
            maxWidth: "34ch",
          }}
        >
          See what moved in your portfolio today, and why.
        </h2>
        <Link
          href="/signup"
          className="landing-cta-primary"
          style={{
            fontSize: "14px",
            fontWeight: 600,
            color: "#fff",
            background: "var(--color-accent-primary)",
            border: "1px solid var(--color-accent-primary)",
            borderRadius: "var(--radius-control, 8px)",
            padding: "12px 22px",
            textDecoration: "none",
            whiteSpace: "nowrap",
            flexShrink: 0,
          }}
        >
          Start free
        </Link>
      </div>
    </section>
  );
}
