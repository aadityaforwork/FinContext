"use client";

import { useState, useEffect, useRef } from "react";

/**
 * Living numbers — count-up + tween primitives.
 * ----------------------------------------------
 * Pure frontend, zero deps. A number rendered through <AnimatedNumber> counts
 * up from `from` on first mount, then smoothly tweens whenever `value` changes.
 * `<Reveal>` staggers a list so rows cascade in instead of snapping.
 *
 * Hydration-safe: the initial render is always `from` (server and client
 * agree), and the animation only kicks in inside an effect. Honours
 * prefers-reduced-motion by snapping straight to the target.
 */

const EASE_OUT_CUBIC = (t) => 1 - Math.pow(1 - t, 3);

function prefersReducedMotion() {
  if (typeof window === "undefined") return false;
  return window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;
}

/**
 * useTween — animate a number toward `target`.
 *   - first mount: counts up from `from`
 *   - subsequent changes: tweens from the currently displayed value
 * Returns the live display value (a float mid-flight).
 */
export function useTween(target, { duration = 900, from = 0 } = {}) {
  const [display, setDisplay] = useState(from);
  const rafRef = useRef(null);
  const displayRef = useRef(from);

  // keep a ref of the latest displayed value so the effect can read it
  // without listing `display` as a dependency (which would restart the tween).
  displayRef.current = display;

  useEffect(() => {
    if (target == null || Number.isNaN(target)) {
      setDisplay(target);
      return;
    }
    if (prefersReducedMotion()) {
      setDisplay(target);
      return;
    }
    const start = displayRef.current ?? 0;
    const delta = target - start;
    if (delta === 0) return;

    let startTs = null;
    const step = (ts) => {
      if (startTs == null) startTs = ts;
      const t = Math.min((ts - startTs) / duration, 1);
      setDisplay(start + delta * EASE_OUT_CUBIC(t));
      if (t < 1) rafRef.current = requestAnimationFrame(step);
    };
    rafRef.current = requestAnimationFrame(step);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [target, duration]);

  return display;
}

/**
 * <AnimatedNumber value={n} format={fn} />
 * `format` receives the live float and returns the string to render. If
 * omitted, the value is rounded to an integer.
 */
export function AnimatedNumber({
  value,
  format,
  duration = 900,
  from = 0,
  className,
  style,
}) {
  const display = useTween(value, { duration, from });
  const text =
    display == null || Number.isNaN(display)
      ? format
        ? format(display)
        : "—"
      : format
        ? format(display)
        : String(Math.round(display));
  return (
    <span
      className={className}
      style={{ fontVariantNumeric: "tabular-nums", ...style }}
    >
      {text}
    </span>
  );
}

/**
 * <Reveal index={i}> — wraps a list row so it fades+rises in, staggered by
 * `index * step` ms. Uses the `fadeInUp` keyframe from globals.css.
 */
export function Reveal({ index = 0, step = 40, children, className, style }) {
  return (
    <div
      className={className}
      style={{
        animation: "fadeInUp 0.42s cubic-bezier(0.22, 1, 0.36, 1) both",
        animationDelay: `${index * step}ms`,
        ...style,
      }}
    >
      {children}
    </div>
  );
}
