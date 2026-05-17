"use client";

/**
 * NewsWireLoader — Editorial Quiet edition.
 *
 * The news feed has nothing to "actively show" while it loads (no SSE steps),
 * so the old Wire-Scanner card with cycling sources + counters felt manufactured.
 * This rebuild leans the other way: restraint, negative space, the quote as
 * hero. Reads like an FT / Economist / Bloomberg Pro loading state, not a
 * trading-app dashboard.
 *
 * Composition (top → bottom):
 *   1. hairline rule (centered, ~33% width, very faint)
 *   2. the quote, large serif italic, hand-picked once per mount
 *   3. author in small-caps tracking
 *   4. hairline rule
 *   5. a single thin SVG arc that rotates slowly (the only motion on screen)
 *   6. one quiet status line: "Reading the wire · T+00:14"
 *
 * No counters. No chips. No cards. No flashing. No emojis. One color (the
 * accent indigo, used once on the arc). Everything else is the existing
 * text-secondary / text-muted scale on the dark surface.
 */

import { useEffect, useState } from "react";
import { pickLoaderQuote } from "../lib/loaderQuotes";

export default function NewsWireLoader() {
  // Quote is picked once on mount — never re-rolls during the load, so the
  // user reads the same line they first saw (premium = stillness, not churn).
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

  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        textAlign: "center",
        padding: "48px 28px",
        gap: "26px",
        minHeight: "320px",
      }}
    >
      {/* Top hairline — narrow, centered, very faint. */}
      <Hairline />

      {/* The quote. Serif italic, the only loud thing on the page. We don't
          force a webfont — system serif gives us Georgia / Times New Roman
          which read luxe on dark surfaces without a runtime font fetch. */}
      <figure
        style={{
          maxWidth: "440px",
          margin: 0,
          display: "flex",
          flexDirection: "column",
          gap: "20px",
          animation: "nw-fade-in 1.2s ease-out both",
        }}
      >
        <blockquote
          style={{
            margin: 0,
            fontFamily:
              "var(--font-serif)",
            fontStyle: "italic",
            fontWeight: 400,
            fontSize: "19px",
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

      {/* Bottom hairline mirrors the top. */}
      <Hairline />

      {/* The one moving thing on the page. A single thin arc that rotates
          slowly. SVG so the stroke stays crisp at any DPR; CSS for rotation
          so React doesn't re-render. */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: "14px",
          marginTop: "4px",
        }}
      >
        <SlowArc size={26} />
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
          Reading the wire&nbsp;&nbsp;·&nbsp;&nbsp;T+{mm}:{ss}
        </div>
      </div>

      <style jsx>{`
        @keyframes nw-fade-in {
          from { opacity: 0; transform: translateY(4px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Hairline — narrow, centered horizontal rule used above/below the quote.
// Kept as its own component so the width / opacity / centering is consistent
// at both positions without copy-pasting style objects.
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
// SlowArc — the single motion element. One thin SVG arc that rotates over
// 3.6s with linear easing. Stroke is the accent color at low opacity so it
// reads as a "presence" not a busy spinner.
// ---------------------------------------------------------------------------
function SlowArc({ size = 24 }) {
  const stroke = 1.6;
  const r = (size - stroke) / 2;
  const c = size / 2;
  // 75° arc — long enough to register motion, short enough to feel restrained.
  const dash = (2 * Math.PI * r) * (75 / 360);
  const gap  = (2 * Math.PI * r) - dash;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {/* Faint full ring as a ghost — sets the radius without dominating. */}
      <circle
        cx={c} cy={c} r={r}
        fill="none"
        stroke="rgba(255,255,255,0.06)"
        strokeWidth={stroke}
      />
      {/* Rotating arc. Origin is the SVG center; CSS animation drives rotation. */}
      <circle
        className="nw-arc"
        cx={c} cy={c} r={r}
        fill="none"
        stroke="var(--color-accent-primary)"
        strokeOpacity="0.85"
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={`${dash} ${gap}`}
        style={{ transformOrigin: `${c}px ${c}px` }}
      />
      <style jsx>{`
        @keyframes nw-arc-spin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
        :global(.nw-arc) {
          animation: nw-arc-spin 3.6s linear infinite;
        }
      `}</style>
    </svg>
  );
}
