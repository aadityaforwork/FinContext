"use client";

/**
 * PipelineDiagram — the hero's enrichment (Hallmark Tier A/B: hand-built
 * SVG + CSS, no asset, no library). Not a screenshot — this product has
 * no public marketing screenshot to show honestly, so instead of faking
 * one, the diagram draws the actual four-stage pipeline described in
 * HowItWorks.jsx below it. One arrow (data → cited claim, the core
 * "grounding" transition) carries a live travelling-dash flow; the rest
 * are static. Every label mirrors the real stage names — this is
 * information design, not decoration, and it survives being deleted
 * (the hero still reads fine on headline + lede + CTA alone).
 */
export default function PipelineDiagram() {
  return (
    <svg
      className="pipeline"
      viewBox="0 0 800 190"
      role="img"
      aria-label="The four-stage pipeline: compute, cite, verify, grade"
    >
      {/* 1.0 COMPUTE */}
      <g className="pipeline__group pipeline__group--a">
        <rect className="pipeline__box" x="8" y="50" width="150" height="90" />
        <text className="pipeline__num" x="24" y="72">1.0</text>
        <text className="pipeline__label" x="24" y="98">Compute</text>
        <text className="pipeline__cap" x="24" y="116">deterministic</text>
      </g>

      <path
        className="pipeline__arrow pipeline__arrow--live"
        d="M 158 95 L 208 95"
        markerEnd="url(#pipeline-arrowhead)"
      />

      {/* 2.0 CITE */}
      <g className="pipeline__group pipeline__group--b">
        <rect className="pipeline__box pipeline__box--live" x="210" y="50" width="160" height="90" />
        <text className="pipeline__num" x="226" y="72">2.0</text>
        <text className="pipeline__label" x="226" y="98">Cite</text>
        <text className="pipeline__cap" x="226" y="116">or say “unknown”</text>
      </g>

      <path
        className="pipeline__arrow"
        d="M 370 95 L 420 95"
        markerEnd="url(#pipeline-arrowhead-muted)"
      />

      {/* 3.0 VERIFY */}
      <g className="pipeline__group pipeline__group--c">
        <rect className="pipeline__box" x="422" y="50" width="150" height="90" />
        <text className="pipeline__num" x="438" y="72">3.0</text>
        <text className="pipeline__label" x="438" y="98">Verify</text>
        <text className="pipeline__cap" x="438" y="116">second pass</text>
      </g>

      <path
        className="pipeline__arrow"
        d="M 572 95 L 622 95"
        markerEnd="url(#pipeline-arrowhead-muted)"
      />

      {/* 4.0 GRADE */}
      <g className="pipeline__group pipeline__group--d">
        <rect className="pipeline__box" x="624" y="50" width="168" height="90" />
        <text className="pipeline__num" x="640" y="72">4.0</text>
        <text className="pipeline__label" x="640" y="98">Grade</text>
        <text className="pipeline__cap" x="640" y="116">public, 1–20d</text>
      </g>

      <defs>
        <marker id="pipeline-arrowhead" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6" style={{ fill: "var(--color-accent-primary)", stroke: "none" }} />
        </marker>
        <marker id="pipeline-arrowhead-muted" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6" style={{ fill: "var(--border-strong)", stroke: "none" }} />
        </marker>
      </defs>
    </svg>
  );
}
