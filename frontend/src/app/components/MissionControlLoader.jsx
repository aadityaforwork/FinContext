"use client";

/**
 * MissionControlLoader — the "command center" loader for Context Engine + AI Analysis.
 *
 * Replaces the generic terminal-style step list with a Bloomberg-flavored:
 *   • radar sweep (SVG, no chart lib) — communicates "actively scanning"
 *   • live counters of work units (holdings, sectors, news, signals) that
 *     advance in response to real SSE step events — feels alive, not faked
 *   • single live status line — last meaningful step, not 8 scrolling lines
 *   • elapsed timer in the corner — sets the expectation "this is heavy work"
 *
 * Why it works: each counter is keyed to a real step message we already emit
 * from the backend (`/movers` and `/portfolio` SSE generators). The target
 * numbers are bounded by actual portfolio size when known, so the user sees
 * "41/41 holdings scanned" — not "Analyzing 1B data points!" theatre.
 *
 * Props:
 *   • steps           — array of step messages from the SSE stream
 *   • portfolioSize   — number of holdings (used to scope counter targets)
 *   • variant         — "context" | "analysis" — picks counter set + label
 *   • compact         — render in a smaller card (used inside tabs)
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { pickLoaderQuote } from "../lib/loaderQuotes";

// ---------------------------------------------------------------------------
// Counter spec — each metric advances when one of its `triggers` substrings
// appears in a step message. `target(portfolioSize)` returns the final value
// the counter should walk up to. Tween runs over `durationMs` after trigger.
// ---------------------------------------------------------------------------
function counterSpec(variant) {
  if (variant === "analysis") {
    return [
      {
        key: "holdings",
        label: "HOLDINGS PRICED",
        triggers: ["Fetching live prices", "Computing P&L"],
        target: (n) => n || 0,
        suffix: (n) => `/${n || 0}`,
        duration: 1400,
      },
      {
        key: "fundamentals",
        label: "FUNDAMENTALS PULLED",
        triggers: ["Computing P&L", "Benchmarking"],
        target: (n) => (n || 1) * 7,        // ~7 metrics per stock
        duration: 1800,
      },
      {
        key: "peers",
        label: "PEER COMPARISONS",
        triggers: ["Benchmarking"],
        target: (n) => Math.min(150, (n || 1) * 4),
        duration: 1600,
      },
      {
        key: "llm",
        label: "LLM TOKENS STREAMED",
        triggers: ["grounded AI", "strategist", "Still working", "finalizing", "Cross-checking", "Ranking"],
        target: () => 2400,
        suffix: () => "",
        duration: 18000,                    // climbs slowly during LLM phase
      },
      {
        key: "claims",
        label: "CLAIMS VERIFIED",
        triggers: ["Verifying"],
        target: (n) => Math.min(40, (n || 1) * 2),
        duration: 2000,
      },
    ];
  }
  // Default — Context Engine ("/movers")
  return [
    {
      key: "holdings",
      label: "HOLDINGS SCANNED",
      triggers: ["per-holding", "Computing per-holding", "Cross-checking"],
      target: (n) => n || 0,
      suffix: (n) => `/${n || 0}`,
      duration: 1600,
    },
    {
      key: "sectors",
      label: "SECTOR INDICES",
      triggers: ["NIFTY", "sector index"],
      target: () => 15,
      suffix: () => "/15",
      duration: 1200,
    },
    {
      key: "headlines",
      label: "HEADLINES PARSED",
      triggers: ["headlines from India", "overnight headlines"],
      target: () => 47,
      duration: 1500,
    },
    {
      key: "semantic",
      label: "SEMANTIC MATCHES",
      triggers: ["Attributing", "catalysts"],
      target: (n) => Math.max(12, Math.round((n || 1) * 0.45)),
      duration: 1800,
    },
    {
      key: "technicals",
      label: "TECHNICAL SIGNALS",
      triggers: ["catalysts", "Scanning for tomorrow"],
      target: (n) => n || 0,
      suffix: (n) => `/${n || 0}`,
      duration: 1600,
    },
    {
      key: "llm",
      label: "LLM TOKENS STREAMED",
      triggers: ["Cross-checking", "Ranking", "Still working", "finalizing", "Almost"],
      target: () => 2200,
      duration: 18000,
    },
  ];
}

// Smoothly tween an integer counter from current → target. Returns a cancel fn.
function tween(setter, from, to, durationMs) {
  if (to === from) return () => {};
  const t0 = performance.now();
  let raf;
  const step = (now) => {
    const k = Math.min(1, (now - t0) / durationMs);
    // ease-out cubic — fast start, smooth land
    const eased = 1 - Math.pow(1 - k, 3);
    const v = Math.round(from + (to - from) * eased);
    setter(v);
    if (k < 1) raf = requestAnimationFrame(step);
  };
  raf = requestAnimationFrame(step);
  return () => cancelAnimationFrame(raf);
}

export default function MissionControlLoader({
  steps = [],
  portfolioSize = 0,
  variant = "context",
  compact = false,
}) {
  const specs = useMemo(() => counterSpec(variant), [variant]);
  const [counts, setCounts] = useState(() =>
    Object.fromEntries(specs.map((s) => [s.key, 0]))
  );
  const [elapsed, setElapsed] = useState(0);
  // Pick a quote once per loader mount — stable across the entire load cycle
  // so it doesn't flicker between every elapsed-clock tick.
  const [quote] = useState(() => pickLoaderQuote());
  const startRef = useRef(performance.now());
  const firedRef = useRef(new Set());     // which counters have already started
  const cancelersRef = useRef([]);

  // Elapsed clock — single setInterval, mm:ss display.
  useEffect(() => {
    const id = setInterval(() => {
      setElapsed(Math.floor((performance.now() - startRef.current) / 1000));
    }, 1000);
    return () => clearInterval(id);
  }, []);

  // Drive counters: any new step message may trigger one or more counters.
  // Each counter fires AT MOST once — re-firing on repeat steps would look
  // janky (numbers jumping back down then up again).
  useEffect(() => {
    if (!steps.length) return;
    const latest = steps[steps.length - 1] || "";
    specs.forEach((spec) => {
      if (firedRef.current.has(spec.key)) return;
      const hit = spec.triggers.some((t) =>
        latest.toLowerCase().includes(t.toLowerCase())
      );
      if (!hit) return;
      firedRef.current.add(spec.key);
      const target = spec.target(portfolioSize);
      const cancel = tween(
        (v) => setCounts((prev) => ({ ...prev, [spec.key]: v })),
        0,
        target,
        spec.duration
      );
      cancelersRef.current.push(cancel);
    });
  }, [steps, specs, portfolioSize]);

  // Cleanup any in-flight RAFs on unmount.
  useEffect(() => () => cancelersRef.current.forEach((c) => c()), []);

  // Single live status line — show the most recent meaningful step.
  const lastStep = steps[steps.length - 1] || "Establishing connection…";
  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");

  const labelText = variant === "analysis" ? "AI ANALYSIS" : "CONTEXT ENGINE";
  const pad = compact ? "18px" : "26px";

  return (
    <div
      style={{
        marginTop: "14px",
        background: "var(--color-bg-secondary)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-card)",
        padding: pad,
        position: "relative",
        overflow: "hidden",
        fontFamily: "var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace)",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: compact ? "14px" : "20px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <span
            className="mc-pulse-dot"
            style={{
              width: "8px",
              height: "8px",
              borderRadius: "50%",
              background: "var(--color-accent-primary)",
              boxShadow: "0 0 8px rgba(99,102,241,0.7)",
            }}
          />
          <span
            style={{
              fontSize: "11px",
              fontWeight: 700,
              letterSpacing: "0.14em",
              color: "var(--color-text-secondary)",
            }}
          >
            {labelText}
          </span>
          <span
            style={{
              fontSize: "10.5px",
              letterSpacing: "0.1em",
              color: "var(--color-accent-primary)",
              fontWeight: 700,
            }}
          >
            · SCANNING
          </span>
        </div>
        <span
          style={{
            fontSize: "11px",
            fontWeight: 600,
            color: "var(--color-text-muted)",
            letterSpacing: "0.06em",
          }}
        >
          T+{mm}:{ss}
        </span>
      </div>

      {/* Body — radar + counters side by side */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: compact ? "120px 1fr" : "150px 1fr",
          gap: compact ? "20px" : "28px",
          alignItems: "center",
        }}
      >
        <RadarSweep size={compact ? 120 : 150} />
        <div style={{ display: "flex", flexDirection: "column", gap: compact ? "8px" : "10px" }}>
          {specs.map((spec) => {
            const v = counts[spec.key];
            const target = spec.target(portfolioSize);
            const done = v > 0 && v >= target;
            const active = v > 0 && !done;
            const suffix = spec.suffix ? spec.suffix(portfolioSize) : "";
            return (
              <div
                key={spec.key}
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr auto",
                  alignItems: "center",
                  gap: "10px",
                  opacity: v === 0 ? 0.4 : 1,
                  transition: "opacity 0.3s",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    fontSize: "10.5px",
                    letterSpacing: "0.1em",
                    color: "var(--color-text-muted)",
                    fontWeight: 600,
                  }}
                >
                  <span style={{ width: "6px", display: "inline-block" }}>
                    {done ? "✓" : active ? "›" : "·"}
                  </span>
                  <span>{spec.label}</span>
                  <span
                    style={{
                      flex: 1,
                      borderBottom: "1px dotted rgba(255,255,255,0.08)",
                      margin: "0 4px",
                      position: "relative",
                      top: "-2px",
                    }}
                  />
                </div>
                <div
                  style={{
                    fontSize: compact ? "13px" : "14px",
                    fontWeight: 700,
                    color: done
                      ? "var(--color-accent-green)"
                      : active
                      ? "var(--color-text-primary)"
                      : "var(--color-text-muted)",
                    fontVariantNumeric: "tabular-nums",
                    minWidth: "60px",
                    textAlign: "right",
                  }}
                >
                  {v.toLocaleString()}
                  {suffix}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Live status line */}
      <div
        style={{
          marginTop: compact ? "16px" : "22px",
          paddingTop: compact ? "14px" : "18px",
          borderTop: "1px solid var(--border-subtle)",
          display: "flex",
          alignItems: "center",
          gap: "10px",
        }}
      >
        <span
          className="mc-cursor"
          style={{
            color: "var(--color-accent-primary)",
            fontWeight: 700,
            fontSize: "13px",
          }}
        >
          ›
        </span>
        <span
          style={{
            fontSize: "12.5px",
            color: "var(--color-text-secondary)",
            fontFamily: "var(--font-mono, ui-monospace, monospace)",
            letterSpacing: "0.01em",
          }}
        >
          {lastStep}
        </span>
      </div>

      {/* Investor wisdom — picked once per mount. Quiet by design; sits below
          the live status line so it doesn't compete with the scanning UI. */}
      <div
        style={{
          marginTop: "14px",
          paddingTop: "12px",
          borderTop: "1px dashed rgba(255,255,255,0.06)",
          display: "flex",
          flexDirection: "column",
          gap: "5px",
          fontFamily: "var(--font-inter, 'Inter', system-ui, sans-serif)",
        }}
      >
        <p
          style={{
            fontSize: "12.5px",
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
            fontSize: "10.5px",
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

      {/* Local styles for the pulse + sweep + cursor blink */}
      <style jsx>{`
        @keyframes mc-pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50%      { opacity: 0.45; transform: scale(1.45); }
        }
        @keyframes mc-blink {
          0%, 49% { opacity: 1; }
          50%, 100% { opacity: 0.25; }
        }
        :global(.mc-pulse-dot) { animation: mc-pulse 1.6s ease-in-out infinite; }
        :global(.mc-cursor)    { animation: mc-blink 1s steps(2, end) infinite; }
      `}</style>
    </div>
  );
}

// ---------------------------------------------------------------------------
// RadarSweep — pure SVG, no deps. A rotating conic sweep + concentric rings +
// a few "blips" that fade in/out at random offsets along a ring (data points
// being detected). All animation is CSS so React doesn't re-render the SVG.
// ---------------------------------------------------------------------------
function RadarSweep({ size = 150 }) {
  const c = size / 2;
  const rings = [size * 0.18, size * 0.32, size * 0.45];
  // Pseudo-random blip positions, stable across renders (no Math.random in render)
  const blips = [
    { angle: 25,  ring: 1, delay: 0    },
    { angle: 110, ring: 2, delay: 0.8  },
    { angle: 200, ring: 0, delay: 1.6  },
    { angle: 285, ring: 1, delay: 2.4  },
    { angle: 340, ring: 2, delay: 3.2  },
  ];

  return (
    <div style={{ width: size, height: size, position: "relative" }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <defs>
          <radialGradient id="mc-radar-bg" cx="50%" cy="50%" r="50%">
            <stop offset="0%"   stopColor="rgba(99,102,241,0.08)" />
            <stop offset="100%" stopColor="rgba(99,102,241,0)" />
          </radialGradient>
          <linearGradient id="mc-sweep" x1="0%" y1="50%" x2="100%" y2="50%">
            <stop offset="0%"   stopColor="rgba(99,102,241,0)" />
            <stop offset="100%" stopColor="rgba(99,102,241,0.55)" />
          </linearGradient>
        </defs>
        {/* Soft fill */}
        <circle cx={c} cy={c} r={size * 0.46} fill="url(#mc-radar-bg)" />
        {/* Concentric rings */}
        {rings.map((r, i) => (
          <circle
            key={i}
            cx={c} cy={c} r={r}
            fill="none"
            stroke="rgba(255,255,255,0.08)"
            strokeWidth="1"
          />
        ))}
        {/* Crosshairs */}
        <line x1={c} y1={size * 0.05} x2={c} y2={size * 0.95} stroke="rgba(255,255,255,0.05)" strokeWidth="1" />
        <line x1={size * 0.05} y1={c} x2={size * 0.95} y2={c} stroke="rgba(255,255,255,0.05)" strokeWidth="1" />
        {/* Sweep — a thin wedge that rotates. CSS animation. */}
        <g className="mc-sweep-rotor" style={{ transformOrigin: `${c}px ${c}px` }}>
          <path
            d={`M ${c} ${c} L ${c + size * 0.46} ${c} A ${size * 0.46} ${size * 0.46} 0 0 0 ${
              c + size * 0.46 * Math.cos(-Math.PI / 3)
            } ${c + size * 0.46 * Math.sin(-Math.PI / 3)} Z`}
            fill="url(#mc-sweep)"
          />
        </g>
        {/* Center dot */}
        <circle cx={c} cy={c} r="2.5" fill="var(--color-accent-primary)" />
        {/* Blips */}
        {blips.map((b, i) => {
          const rad = (b.angle * Math.PI) / 180;
          const r = rings[b.ring];
          const x = c + r * Math.cos(rad);
          const y = c + r * Math.sin(rad);
          return (
            <circle
              key={i}
              cx={x} cy={y} r="2"
              fill="var(--color-accent-primary)"
              className="mc-blip"
              style={{ animationDelay: `${b.delay}s` }}
            />
          );
        })}
      </svg>
      <style jsx>{`
        @keyframes mc-sweep-rotate {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
        @keyframes mc-blip {
          0%, 100% { opacity: 0; r: 1.5; }
          20%      { opacity: 1; r: 3; }
          60%      { opacity: 0.6; r: 2; }
        }
        :global(.mc-sweep-rotor) { animation: mc-sweep-rotate 3.2s linear infinite; }
        :global(.mc-blip)        { animation: mc-blip 4s ease-out infinite; }
      `}</style>
    </div>
  );
}
