"use client";

/**
 * HowItWorks — F4 Step sequence (macrostructure: Narrative Workflow).
 * This is the one section where numbered stage labels are earned: the
 * product genuinely runs data through these four stages in order before
 * anything reaches the user. Content translates real backend mechanisms
 * (grounding contract, deterministic compute, self-verification, the
 * outcome ledger) into plain language — nothing here is aspirational.
 */
const STAGES = [
  {
    n: "1.0",
    title: "Compute first.",
    body:
      "Deterministic services calculate the numbers — signal strength, risk metrics, technicals, portfolio exposure — before any model sees the request. The model is never asked to do arithmetic.",
  },
  {
    n: "2.0",
    title: "Narrate only what’s grounded.",
    body:
      "The model cites a source for every figure it uses and rates its own confidence low, medium, or high. If nothing in the data supports a number, it says so instead of estimating one.",
  },
  {
    n: "3.0",
    title: "Check the claim.",
    body:
      "High-stakes analyses get a second pass — a separate check that grades the first answer against the same underlying data before it reaches you. Some flows split the work across more than one agent: one extracts a claim, another quantifies it.",
  },
  {
    n: "4.0",
    title: "Grade it in public.",
    body:
      "Every directional call is logged the moment it’s made, then automatically checked against real closing prices 1, 5, and 20 days later. The full record is public — not summarised, not curated.",
  },
];

export default function HowItWorks() {
  return (
    <section
      id="how"
      style={{
        padding: "var(--space-2xl) clamp(1rem, 4vw, 2.5rem)",
        maxWidth: "1180px",
        margin: "0 auto",
        borderTop: "1px solid var(--border-subtle)",
        scrollMarginTop: "calc(var(--bar-h) + var(--space-md))",
      }}
    >
      <h2
        style={{
          fontFamily: "var(--font-serif)",
          fontSize: "clamp(1.875rem, 2.5vw + 1rem, 2.75rem)",
          fontWeight: 700,
          lineHeight: 1.1,
          letterSpacing: "-0.01em",
          color: "var(--color-text-primary)",
          margin: "0 0 var(--space-2xl)",
          maxWidth: "40ch",
        }}
      >
        Built to narrate, not to guess
      </h2>

      <ol
        style={{
          listStyle: "none",
          margin: 0,
          padding: 0,
          display: "grid",
          gap: 0,
        }}
      >
        {STAGES.map((stage, i) => (
          <li
            key={stage.n}
            className="landing-reveal"
            style={{
              "--i": i,
              display: "grid",
              gridTemplateColumns: "5rem 1fr",
              gap: "var(--space-lg)",
              padding: "var(--space-lg) 0",
              borderTop: i === 0 ? "1px solid var(--border-subtle)" : "none",
              borderBottom: "1px solid var(--border-subtle)",
            }}
          >
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "20px",
                fontWeight: 600,
                color: "var(--color-accent-secondary)",
                letterSpacing: "-0.02em",
              }}
            >
              {stage.n}
            </span>
            <div>
              <h3
                style={{
                  fontSize: "18px",
                  fontWeight: 700,
                  color: "var(--color-text-primary)",
                  margin: "0 0 6px",
                }}
              >
                {stage.title}
              </h3>
              <p
                style={{
                  fontSize: "14px",
                  lineHeight: 1.6,
                  color: "var(--color-text-secondary)",
                  maxWidth: "60ch",
                  margin: 0,
                }}
              >
                {stage.body}
              </p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
