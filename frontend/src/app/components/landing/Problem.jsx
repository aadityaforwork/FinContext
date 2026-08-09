"use client";

/**
 * Problem — plain section head, no eyebrow (this content isn't ordinal,
 * so a numbered tag here would be decoration, not information — see
 * Hallmark's eyebrow-default-off rule). Left-biased, not centred.
 */
export default function Problem() {
  return (
    <section
      style={{
        padding: "var(--space-xl) clamp(1rem, 4vw, 2.5rem) var(--space-2xl)",
        maxWidth: "1180px",
        margin: "0 auto",
        borderTop: "1px solid var(--border-subtle)",
      }}
    >
      <div style={{ maxWidth: "62ch" }}>
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
          What your portfolio tracker won&rsquo;t tell you
        </h2>
        <p
          style={{
            fontSize: "15px",
            lineHeight: 1.65,
            color: "var(--color-text-secondary)",
            margin: 0,
          }}
        >
          Price and P&amp;L are the easy part — every app shows those. Why a
          stock moved is harder: an earnings beat two sectors over, a rate
          decision made in Washington, a single analyst note that changed the
          mood. Today, finding out means switching tabs, scrolling social
          media, or waiting for someone else to explain it a day later.
        </p>
      </div>
    </section>
  );
}
