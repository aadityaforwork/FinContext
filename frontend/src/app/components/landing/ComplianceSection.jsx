"use client";

import ComplianceFooter from "../ComplianceFooter";

/**
 * ComplianceSection — quiet on purpose. Not a pitch, not styled to compete
 * with the CTA above it. States the one real, verifiable claim (compliance
 * is enforced in the API, not just printed on the page) and then hands off
 * to the exact, legally-reviewed disclaimer text every other view in the
 * app already uses — reused verbatim, never rewritten.
 */
export default function ComplianceSection() {
  return (
    <section
      style={{
        padding: "var(--space-xl) clamp(1rem, 4vw, 2.5rem) 0",
        maxWidth: "1180px",
        margin: "0 auto",
        borderTop: "1px solid var(--border-subtle)",
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
        Compliance
      </p>
      <p
        style={{
          fontSize: "14px",
          lineHeight: 1.6,
          color: "var(--color-text-secondary)",
          maxWidth: "62ch",
          margin: 0,
        }}
      >
        FinContext doesn&rsquo;t issue buy or sell calls or target prices —
        you&rsquo;ll see signal strength, valuation bands, and peer rank
        instead. That restriction is enforced where the response is built,
        in the API, not just printed at the bottom of the page.
      </p>
      <ComplianceFooter />
    </section>
  );
}
