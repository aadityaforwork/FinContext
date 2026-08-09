"use client";

import Link from "next/link";
import PipelineDiagram from "./PipelineDiagram";
import VerifiedStamp from "./VerifiedStamp";
import SignalCard from "./SignalCard";

/**
 * Hero — Marquee-weighted headline + lede + CTAs, full-width below it.
 * Enrichment: hand-built pipeline diagram (PipelineDiagram.jsx) + a
 * studied-DNA accent (VerifiedStamp.jsx) — Hallmark Tier A/B, no
 * screenshot exists to show honestly, so both are drawn, not faked.
 * Headline carries two registers via weight + colour, not italics —
 * Hallmark's typography-purity rule (no italic headers) is non-negotiable
 * even where the studied reference used an italic script second line.
 */
export default function Hero() {
  return (
    <section
      style={{
        padding: "var(--space-xl) clamp(1rem, 4vw, 2.5rem) var(--space-3xl)",
        maxWidth: "1180px",
        margin: "0 auto",
      }}
    >
      <div className="hero-grid">
        <div className="landing-reveal" style={{ "--i": 0 }}>
          <p
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              fontFamily: "var(--font-mono)",
              fontSize: "11px",
              fontWeight: 600,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              color: "var(--color-accent-secondary)",
              margin: "0 0 var(--space-md)",
            }}
          >
            <span aria-hidden="true">↗</span> NSE &amp; BSE coverage
          </p>
          <h1
            style={{
              fontFamily: "var(--font-serif)",
              fontWeight: 700,
              fontSize: "clamp(2.75rem, 5vw + 1rem, 5.25rem)",
              lineHeight: 1.02,
              letterSpacing: "-0.01em",
              margin: "0 0 var(--space-lg)",
              overflowWrap: "anywhere",
            }}
          >
            <span style={{ color: "var(--color-text-primary)" }}>Your portfolio moved.</span>
            <br />
            <span style={{ color: "var(--color-text-secondary)", fontWeight: 400 }}>
              Here&rsquo;s why.
            </span>
          </h1>
          <p
            style={{
              fontSize: "17px",
              lineHeight: 1.6,
              color: "var(--color-text-secondary)",
              maxWidth: "46ch",
              margin: "0 0 var(--space-xl)",
            }}
          >
            Your broker&rsquo;s app tells you the price moved. It doesn&rsquo;t tell
            you why. FinContext ties every move in your holdings to a catalyst —
            an earnings call, a sector headline, an overnight macro shift — and
            explains it in plain language, sourced back to where it came from.
          </p>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-lg)", flexWrap: "wrap" }}>
            <Link
              href="/signup"
              className="landing-cta-primary"
              style={{
                fontSize: "14.5px",
                fontWeight: 600,
                color: "#fff",
                background: "var(--color-accent-primary)",
                border: "1px solid var(--color-accent-primary)",
                borderRadius: "var(--radius-control, 8px)",
                padding: "13px 22px",
                textDecoration: "none",
                whiteSpace: "nowrap",
                display: "inline-block",
              }}
            >
              Start free
            </Link>
            <Link
              href="/accuracy"
              style={{
                fontSize: "13.5px",
                fontWeight: 600,
                color: "var(--color-text-secondary)",
                textDecoration: "underline",
                textUnderlineOffset: "3px",
                textDecorationColor: "var(--border-strong)",
                whiteSpace: "nowrap",
                display: "inline-block",
              }}
            >
              Track record →
            </Link>
          </div>
        </div>

        <div className="landing-reveal" style={{ "--i": 1 }}>
          <SignalCard />
        </div>
      </div>

      <div
        className="landing-reveal"
        style={{
          "--i": 2,
          position: "relative",
          marginTop: "var(--space-2xl)",
          background: "var(--color-bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-card)",
          padding: "var(--space-lg) var(--space-lg) var(--space-md)",
        }}
      >
        <VerifiedStamp />
        <p
          style={{
            fontSize: "10px",
            fontWeight: 700,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: "var(--color-text-muted)",
            margin: "0 0 var(--space-md)",
          }}
        >
          What actually happens to your request
        </p>
        <div className="pipeline-scroller">
          <PipelineDiagram />
        </div>
      </div>
    </section>
  );
}
