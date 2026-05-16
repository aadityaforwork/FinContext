"use client";

/**
 * NewsWireLoader — "wire scanner" loader for the News Impact Feed.
 *
 * Why this exists: the news feed is a slow REST endpoint (no SSE steps to
 * count). Plain skeleton bars feel like dead waiting. This loader makes the
 * wait feel like an actively-working newsroom:
 *
 *   • Header: source counter + headline counter ticking up while you watch.
 *     Numbers are bounded plausibly (12-24 sources, 40-80 headlines per
 *     scan) — not "1 trillion data points!" theatre.
 *   • Four "filing slots" build up in staggered stages:
 *       Stage 0  empty slot, faint
 *       Stage 1  source label appears (REUTERS / BLOOMBERG / MINT / ET / ...)
 *       Stage 2  headline + snippet shimmer bars appear
 *       Stage 3  category + impact chips appear
 *       Stage 4  brief green "PARSED" flash, then loops back to stage 1
 *                with a different source (so the wire feels continuous)
 *   • All animation is CSS — no JS RAF, no re-renders during the cycle.
 *
 * The shimmer content is deliberately ABSTRACT (bars, not fake headlines)
 * so a screenshot can't be mistaken for a real news item.
 */

import { useEffect, useState } from "react";
import { pickLoaderQuote } from "../lib/loaderQuotes";

// Real Indian + global wire sources users will recognize. The cycle order
// is randomized once on mount so the loader doesn't look identical across
// dashboard reloads.
const SOURCES = [
  "REUTERS", "BLOOMBERG", "ECON TIMES", "MINT", "CNBC TV18",
  "MONEYCONTROL", "BUSINESS LINE", "BUSINESS STANDARD",
  "PIB INDIA", "RBI", "NDTV PROFIT", "FINANCIAL EXPRESS",
];

const CATEGORIES = [
  { key: "stock_specific", label: "COMPANY", color: "rgba(99,102,241,0.18)",  text: "#a8aaf0" },
  { key: "sector",         label: "SECTOR",  color: "rgba(45,168,190,0.18)",  text: "#7cc7d6" },
  { key: "macro",          label: "MACRO",   color: "rgba(217,154,43,0.18)",  text: "#e3b566" },
  { key: "global",         label: "GLOBAL",  color: "rgba(154,154,163,0.18)", text: "#a4a4ac" },
  { key: "policy",         label: "POLICY",  color: "rgba(217,154,43,0.18)",  text: "#e3b566" },
];

const IMPACTS = [
  { key: "high",   label: "HIGH", color: "#ef4444" },
  { key: "medium", label: "MED",  color: "#f59e0b" },
  { key: "low",    label: "LOW",  color: "#94a3b8" },
];

// Shuffle helper — Fisher-Yates, seeded by Math.random once per mount only.
function shuffled(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

export default function NewsWireLoader({ slots = 4 }) {
  const [sources] = useState(() => shuffled(SOURCES));
  const [headlinesCount, setHeadlinesCount] = useState(0);
  const [sourcesCount, setSourcesCount] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  // Picked once per mount — pairs with the same quote bank used by Mission
  // Control so the two loaders feel like a single product, not two surfaces.
  const [quote] = useState(() => pickLoaderQuote());

  // Header counters — climb plausibly. Headlines climbs faster than sources.
  // Both cap so they look bounded, not infinite.
  useEffect(() => {
    const t0 = performance.now();
    const id = setInterval(() => {
      const sec = (performance.now() - t0) / 1000;
      setElapsed(Math.floor(sec));
      // Headlines: climb to ~64 over 8 seconds, then slow tail.
      setHeadlinesCount((prev) => {
        if (prev >= 64) return prev + (Math.random() < 0.3 ? 1 : 0);
        return Math.min(64, prev + 2);
      });
      // Sources: climb to 24 over ~6 seconds.
      setSourcesCount((prev) => Math.min(24, prev + 1));
    }, 300);
    return () => clearInterval(id);
  }, []);

  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
      {/* Header strip — matches Mission Control language so the two loaders
          feel like a family, not two different products. */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "10px 12px",
          background: "var(--color-bg-secondary)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-control)",
          fontFamily: "var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <span
            className="wire-pulse-dot"
            style={{
              width: "7px",
              height: "7px",
              borderRadius: "50%",
              background: "var(--color-accent-primary)",
              boxShadow: "0 0 6px rgba(99,102,241,0.7)",
            }}
          />
          <span
            style={{
              fontSize: "10px",
              fontWeight: 700,
              letterSpacing: "0.14em",
              color: "var(--color-text-secondary)",
            }}
          >
            FILING WIRE
          </span>
          <span
            style={{
              fontSize: "10px",
              fontWeight: 700,
              letterSpacing: "0.1em",
              color: "var(--color-accent-primary)",
            }}
          >
            · SCANNING
          </span>
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "12px",
            fontSize: "10px",
            color: "var(--color-text-muted)",
            letterSpacing: "0.08em",
            fontWeight: 600,
          }}
        >
          <span>
            <span style={{ color: "var(--color-text-primary)", fontVariantNumeric: "tabular-nums" }}>
              {sourcesCount}
            </span>
            <span style={{ marginLeft: "4px" }}>SRC</span>
          </span>
          <span style={{ opacity: 0.4 }}>·</span>
          <span>
            <span style={{ color: "var(--color-text-primary)", fontVariantNumeric: "tabular-nums" }}>
              {headlinesCount}
            </span>
            <span style={{ marginLeft: "4px" }}>HDL</span>
          </span>
          <span style={{ opacity: 0.4 }}>·</span>
          <span style={{ fontVariantNumeric: "tabular-nums" }}>T+{mm}:{ss}</span>
        </div>
      </div>

      {/* Filing slots — each is a card that staggers through build-up stages. */}
      {Array.from({ length: slots }).map((_, i) => (
        <FilingSlot
          key={i}
          source={sources[i % sources.length]}
          category={CATEGORIES[i % CATEGORIES.length]}
          impact={IMPACTS[i % IMPACTS.length]}
          delaySec={i * 0.35}
        />
      ))}

      {/* Investor wisdom — paired bank with Mission Control. Quiet, italic,
          sits below the wire so it never competes with the scanning UI. */}
      <div
        style={{
          marginTop: "6px",
          paddingTop: "12px",
          borderTop: "1px dashed rgba(255,255,255,0.06)",
          display: "flex",
          flexDirection: "column",
          gap: "5px",
          padding: "12px 12px 4px",
          fontFamily: "var(--font-inter, 'Inter', system-ui, sans-serif)",
        }}
      >
        <p
          style={{
            fontSize: "12px",
            fontStyle: "italic",
            color: "var(--color-text-secondary)",
            lineHeight: 1.45,
            margin: 0,
            letterSpacing: "-0.005em",
          }}
        >
          &ldquo;{quote.text}&rdquo;
        </p>
        <p
          style={{
            fontSize: "10px",
            fontWeight: 600,
            color: "var(--color-text-muted)",
            letterSpacing: "0.06em",
            textTransform: "uppercase",
            margin: 0,
          }}
        >
          — {quote.author}
        </p>
      </div>

      <style jsx>{`
        @keyframes wire-pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50%      { opacity: 0.45; transform: scale(1.4); }
        }
        :global(.wire-pulse-dot) { animation: wire-pulse 1.6s ease-in-out infinite; }
      `}</style>
    </div>
  );
}

// ---------------------------------------------------------------------------
// FilingSlot — one row that morphs through 4 stages over 4s, then loops.
// All timing is CSS so we don't burn React renders during the loader cycle.
// ---------------------------------------------------------------------------
function FilingSlot({ source, category, impact, delaySec }) {
  return (
    <div
      className="wire-slot"
      style={{
        position: "relative",
        background: "var(--color-bg-card)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "10px",
        padding: "12px 14px",
        minHeight: "88px",
        display: "flex",
        flexDirection: "column",
        gap: "8px",
        overflow: "hidden",
        animationDelay: `${delaySec}s`,
      }}
    >
      {/* Source row */}
      <div
        className="wire-source"
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          opacity: 0,
          animationDelay: `${delaySec + 0.3}s`,
        }}
      >
        <span
          style={{
            display: "inline-block",
            width: "5px",
            height: "5px",
            borderRadius: "50%",
            background: "var(--color-accent-primary)",
          }}
        />
        <span
          style={{
            fontFamily: "var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace)",
            fontSize: "9.5px",
            fontWeight: 700,
            letterSpacing: "0.14em",
            color: "var(--color-text-muted)",
          }}
        >
          {source}
        </span>
        <span
          className="wire-status"
          style={{
            fontFamily: "var(--font-mono, ui-monospace, monospace)",
            fontSize: "9.5px",
            fontWeight: 600,
            letterSpacing: "0.1em",
            color: "var(--color-accent-secondary)",
            opacity: 0,
            animationDelay: `${delaySec + 0.55}s`,
          }}
        >
          DECODING…
        </span>
      </div>

      {/* Headline + snippet shimmer bars */}
      <div
        className="wire-headline"
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "6px",
          opacity: 0,
          animationDelay: `${delaySec + 0.7}s`,
        }}
      >
        <ShimmerBar w="78%" h="11px" />
        <ShimmerBar w="55%" h="9px" />
      </div>

      {/* Tag chips — appear last */}
      <div
        className="wire-tags"
        style={{
          display: "flex",
          alignItems: "center",
          gap: "6px",
          marginTop: "auto",
          opacity: 0,
          animationDelay: `${delaySec + 1.1}s`,
        }}
      >
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            padding: "2px 7px",
            borderRadius: "4px",
            background: category.color,
            color: category.text,
            fontSize: "9px",
            fontWeight: 700,
            letterSpacing: "0.1em",
            fontFamily: "var(--font-mono, ui-monospace, monospace)",
          }}
        >
          {category.label}
        </span>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "4px",
            padding: "2px 7px",
            borderRadius: "4px",
            background: `${impact.color}22`,
            color: impact.color,
            fontSize: "9px",
            fontWeight: 700,
            letterSpacing: "0.1em",
            fontFamily: "var(--font-mono, ui-monospace, monospace)",
          }}
        >
          {impact.label}
        </span>
        <span style={{ flex: 1 }} />
        <span
          className="wire-parsed"
          style={{
            fontSize: "9px",
            fontWeight: 700,
            letterSpacing: "0.12em",
            color: "var(--color-accent-green)",
            opacity: 0,
            animationDelay: `${delaySec + 1.5}s`,
            fontFamily: "var(--font-mono, ui-monospace, monospace)",
          }}
        >
          ✓ PARSED
        </span>
      </div>

      {/* Sweep line — narrow gradient that travels left→right over the card,
          tying the news loader visually to the radar sweep in MissionControl. */}
      <div
        className="wire-sweep"
        style={{
          position: "absolute",
          top: 0,
          bottom: 0,
          width: "30%",
          background:
            "linear-gradient(90deg, rgba(99,102,241,0) 0%, rgba(99,102,241,0.10) 50%, rgba(99,102,241,0) 100%)",
          pointerEvents: "none",
          animationDelay: `${delaySec}s`,
        }}
      />

      <style jsx>{`
        /* Each stage fades in once over the cycle. Cycle length 4.4s covers
           the whole build-up + a brief "settled" pause before looping. */
        @keyframes wire-fade {
          0%, 100% { opacity: 0; }
          15%, 88% { opacity: 1; }
        }
        @keyframes wire-sweep-travel {
          0%   { transform: translateX(-100%); }
          70%  { transform: translateX(450%); }
          100% { transform: translateX(450%); }
        }
        :global(.wire-source),
        :global(.wire-status),
        :global(.wire-headline),
        :global(.wire-tags),
        :global(.wire-parsed) {
          animation: wire-fade 4.4s ease-in-out infinite;
        }
        :global(.wire-sweep) {
          animation: wire-sweep-travel 4.4s ease-in-out infinite;
        }
      `}</style>
    </div>
  );
}

function ShimmerBar({ w = "60%", h = "10px" }) {
  return (
    <div
      className="wire-shimmer"
      style={{
        width: w,
        height: h,
        borderRadius: "3px",
        background:
          "linear-gradient(90deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0.10) 50%, rgba(255,255,255,0.04) 100%)",
        backgroundSize: "200% 100%",
      }}
    >
      <style jsx>{`
        @keyframes wire-shimmer-slide {
          0%   { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
        :global(.wire-shimmer) {
          animation: wire-shimmer-slide 2.2s linear infinite;
        }
      `}</style>
    </div>
  );
}
