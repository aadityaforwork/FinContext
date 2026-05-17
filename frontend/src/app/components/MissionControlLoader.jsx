"use client";

/**
 * MissionControlLoader — Editorial Quiet edition (Context + Analysis).
 *
 * Rewritten to match the home news loader's restraint: serif italic quote as
 * hero, hairlines, one motion element, one quiet status line. The Bloomberg
 * radar/counters version felt busy next to the calm news loader; this aligns
 * the whole product on one loading vocabulary.
 *
 * Each variant gets ONE distinguishing signature so they don't feel identical:
 *   • context  → ScanBeam     — a slow horizontal beam crossing a thin grid
 *                              (reads "scanning the market")
 *   • analysis → ThoughtPulse — concentric pulses rippling out from a core
 *                              (reads "deep reasoning")
 *
 * The status line still shows the latest SSE step so the loader feels alive,
 * but it sits as one quiet mono line — no scrolling counters, no chips.
 *
 * Props (unchanged for back-compat):
 *   • steps          — string[] from the SSE stream (last item is shown)
 *   • portfolioSize  — kept for prop compatibility, no longer rendered
 *   • variant        — "context" | "analysis"
 *   • compact        — slightly tighter padding for in-tab use
 */

import { useEffect, useState } from "react";
import { pickLoaderQuote } from "../lib/loaderQuotes";

export default function MissionControlLoader({
  steps = [],
  // eslint-disable-next-line no-unused-vars
  portfolioSize = 0,
  variant = "context",
  compact = false,
}) {
  // One quote per mount — never rerolls, so the user reads the same line they
  // first saw. Stillness > churn.
  const [quote] = useState(() => pickLoaderQuote());
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const t0 = performance.now();
    const id = setInterval(() => {
      setElapsed(Math.floor((performance.now() - t0) / 1000));
    }, 1000);
    return () => clearInterval(id);
  }, []);

  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");

  const lastStep = steps[steps.length - 1] || "Establishing connection…";

  const labelText =
    variant === "analysis" ? "Reasoning through your portfolio" : "Reading the market";

  const pad = compact ? "36px 24px" : "52px 28px";

  return (
    <div
      style={{
        marginTop: "14px",
        background: "var(--color-bg-card)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-card)",
        padding: pad,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        textAlign: "center",
        gap: "26px",
        minHeight: compact ? "300px" : "360px",
      }}
    >
      <Hairline />

      {/* Hero — serif italic quote, system serif for premium feel without a
          runtime webfont fetch. */}
      <figure
        style={{
          maxWidth: "460px",
          margin: 0,
          display: "flex",
          flexDirection: "column",
          gap: "20px",
          animation: "mc-fade-in 1.2s ease-out both",
        }}
      >
        <blockquote
          style={{
            margin: 0,
            fontFamily:
              "var(--font-serif)",
            fontStyle: "italic",
            fontWeight: 400,
            fontSize: compact ? "17px" : "19px",
            lineHeight: 1.55,
            color: "var(--color-text-primary)",
            letterSpacing: "-0.005em",
          }}
        >
          &ldquo;{quote.text}&rdquo;
        </blockquote>
        <figcaption
          style={{
            fontFamily: "var(--font-sans)",
            fontSize: "10.5px",
            fontWeight: 600,
            letterSpacing: "0.22em",
            textTransform: "uppercase",
            color: "var(--color-text-muted)",
          }}
        >
          — {quote.author}
        </figcaption>
      </figure>

      <Hairline />

      {/* Variant signature — the only motion on the page. */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: "16px",
          marginTop: "2px",
        }}
      >
        {variant === "analysis" ? <ThoughtPulse /> : <ScanBeam />}

        <div
          style={{
            fontFamily:
              "var(--font-mono)",
            fontSize: "10.5px",
            fontWeight: 600,
            letterSpacing: "0.16em",
            color: "var(--color-text-muted)",
            textTransform: "uppercase",
          }}
        >
          {labelText}&nbsp;&nbsp;·&nbsp;&nbsp;T+{mm}:{ss}
        </div>

        {/* Live status — single line, very quiet. Truncates so a long step
            message never breaks the layout. */}
        <div
          title={lastStep}
          style={{
            maxWidth: "460px",
            fontFamily:
              "var(--font-mono)",
            fontSize: "11.5px",
            color: "var(--color-text-secondary)",
            letterSpacing: "0.01em",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            opacity: 0.85,
          }}
        >
          › {lastStep}
        </div>
      </div>

      <style jsx>{`
        @keyframes mc-fade-in {
          from { opacity: 0; transform: translateY(4px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Hairline — mirrors the news loader's rule so both loaders feel like the
// same product.
// ---------------------------------------------------------------------------
function Hairline() {
  return (
    <div
      aria-hidden
      style={{
        width: "min(140px, 32%)",
        height: "1px",
        background:
          "linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.16) 50%, transparent 100%)",
      }}
    />
  );
}

// ---------------------------------------------------------------------------
// ScanBeam — Context Engine signature. A thin vertical beam sweeps left→right
// across a faint chart grid. Reads as "scanning the market" without the noise
// of an actual radar.
// ---------------------------------------------------------------------------
function ScanBeam() {
  const w = 200;
  const h = 44;
  return (
    <div style={{ position: "relative", width: w, height: h, overflow: "hidden" }}>
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
        <defs>
          <linearGradient id="mc-beam" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%"   stopColor="rgba(99,102,241,0)" />
            <stop offset="50%"  stopColor="rgba(99,102,241,0.85)" />
            <stop offset="100%" stopColor="rgba(99,102,241,0)" />
          </linearGradient>
        </defs>
        {/* Faint grid — 4 horizontal lines, evenly spaced. */}
        {[0.2, 0.4, 0.6, 0.8].map((k) => (
          <line
            key={k}
            x1="0" y1={h * k} x2={w} y2={h * k}
            stroke="rgba(255,255,255,0.05)"
            strokeWidth="1"
          />
        ))}
        {/* Two faint vertical tick marks at quartiles. */}
        {[0.25, 0.5, 0.75].map((k) => (
          <line
            key={k}
            x1={w * k} y1="0" x2={w * k} y2={h}
            stroke="rgba(255,255,255,0.04)"
            strokeWidth="1"
          />
        ))}
        {/* The beam itself — a thin rect that slides via CSS transform. */}
        <rect
          className="mc-beam-rect"
          x="-3" y="0" width="3" height={h}
          fill="url(#mc-beam)"
        />
      </svg>
      <style jsx>{`
        @keyframes mc-beam-slide {
          0%   { transform: translateX(0); opacity: 0; }
          12%  { opacity: 1; }
          88%  { opacity: 1; }
          100% { transform: translateX(${w + 6}px); opacity: 0; }
        }
        :global(.mc-beam-rect) {
          animation: mc-beam-slide 2.6s cubic-bezier(0.4, 0, 0.2, 1) infinite;
        }
      `}</style>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ThoughtPulse — AI Analysis signature. A still center dot with two concentric
// rings that ripple outward in sequence. Reads as "reasoning" — slow, focused,
// not frantic.
// ---------------------------------------------------------------------------
function ThoughtPulse() {
  const size = 44;
  const c = size / 2;
  return (
    <div style={{ position: "relative", width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* Two outward-ripple rings, staggered. */}
        <circle
          className="mc-ring mc-ring-a"
          cx={c} cy={c} r="6"
          fill="none"
          stroke="var(--color-accent-primary)"
          strokeWidth="1"
        />
        <circle
          className="mc-ring mc-ring-b"
          cx={c} cy={c} r="6"
          fill="none"
          stroke="var(--color-accent-primary)"
          strokeWidth="1"
        />
        {/* Solid core. */}
        <circle cx={c} cy={c} r="3" fill="var(--color-accent-primary)" />
      </svg>
      <style jsx>{`
        @keyframes mc-ripple {
          0%   { r: 4;  opacity: 0.7; }
          80%  { r: 18; opacity: 0;   }
          100% { r: 18; opacity: 0;   }
        }
        :global(.mc-ring) {
          transform-origin: center;
          animation: mc-ripple 2.4s ease-out infinite;
        }
        :global(.mc-ring-b) {
          animation-delay: 1.2s;
        }
      `}</style>
    </div>
  );
}
