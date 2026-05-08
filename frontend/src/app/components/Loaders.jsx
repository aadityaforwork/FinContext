"use client";

/**
 * Shared loading primitives:
 *   <Spinner size="sm|md|lg" />         — animated SVG ring
 *   <Skeleton h w r />                  — single shimmer block
 *   <SkeletonGrid count cols ... />     — grid of skeleton blocks
 *   <LoaderHeader label />              — spinner + "Loading X…" label (use above a skeleton block)
 *   <SkeletonBlock label children />    — convenience: header + skeleton body in one
 */

const SIZES = {
  sm: 14,
  md: 20,
  lg: 28,
};

export function Spinner({ size = "md", color = "var(--color-accent-secondary)", ariaLabel = "Loading" }) {
  const px = SIZES[size] ?? size;
  return (
    <>
      <style>{`
        @keyframes fc-load-rotate { to { transform: rotate(360deg); } }
        @keyframes fc-load-dash {
          0%   { stroke-dasharray: 1, 120; stroke-dashoffset: 0; }
          50%  { stroke-dasharray: 70, 120; stroke-dashoffset: -20; }
          100% { stroke-dasharray: 70, 120; stroke-dashoffset: -90; }
        }
      `}</style>
      <svg
        width={px}
        height={px}
        viewBox="0 0 50 50"
        role="status"
        aria-label={ariaLabel}
        style={{ animation: "fc-load-rotate 1.2s linear infinite", flexShrink: 0 }}
      >
        <circle
          cx="25"
          cy="25"
          r="20"
          fill="none"
          stroke={color}
          strokeWidth="4"
          strokeLinecap="round"
          style={{ animation: "fc-load-dash 1.4s ease-in-out infinite" }}
        />
      </svg>
    </>
  );
}

export function Skeleton({ h = 16, w = "100%", r = 8, style = {} }) {
  return (
    <div
      className="shimmer"
      style={{
        height: typeof h === "number" ? `${h}px` : h,
        width: typeof w === "number" ? `${w}px` : w,
        borderRadius: typeof r === "number" ? `${r}px` : r,
        ...style,
      }}
    />
  );
}

export function SkeletonGrid({ count = 4, h = 100, r = 16, cols = "repeat(auto-fill, minmax(280px, 1fr))", gap = 16 }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: cols, gap: `${gap}px` }}>
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} h={h} r={r} />
      ))}
    </div>
  );
}

export function LoaderHeader({ label = "Loading…", spinnerSize = "sm" }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "10px",
        marginBottom: "12px",
        fontSize: "12px",
        fontWeight: 600,
        color: "var(--color-text-muted)",
        letterSpacing: "0.02em",
      }}
    >
      <Spinner size={spinnerSize} />
      <span>{label}</span>
    </div>
  );
}

export function SkeletonBlock({ label = "Loading…", children }) {
  return (
    <div>
      <LoaderHeader label={label} />
      {children}
    </div>
  );
}
