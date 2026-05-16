"use client";

/**
 * OnboardingTour — Act 3 of the "First Five Minutes" onboarding.
 *
 * After a brand-new user finishes the wizard + sees their First Insight,
 * they land on the real dashboard. This component overlays 3 small
 * "Try this" callouts that anchor to the most important features, one
 * at a time, with their actual data already in view behind the callout:
 *
 *   1. Context Engine card  — "Run this every morning"
 *   2. News Impact Feed     — "Every story tagged with your stake"
 *   3. AI Analysis tab      — "Bull / bear thesis on your top picks"
 *
 * Anchoring: callouts find their target via [data-tour="<key>"] attributes
 * on the dashboard components themselves. If the target isn't in the DOM
 * (e.g. a tab the user hasn't visited yet), the callout skips itself —
 * tour never points at a missing element.
 *
 * Dismissal: any callout's "Got it" button advances. A small "Skip tour"
 * link in the corner bails out of all remaining steps. Either path writes
 * to localStorage so the tour never re-shows for this user.
 *
 * Visual: matches editorial-terminal — mono labels, hairline border,
 * solid accent button. Single subtle pulse on the anchor outline to
 * draw the eye without being obnoxious.
 */

import { useEffect, useLayoutEffect, useState, useCallback } from "react";

const STORAGE_KEY = "fincontext_tour_seen_v1";

// Steps in display order. `target` matches the `data-tour` attribute on
// the dashboard element we want to highlight; `body` is the callout copy.
const STEPS = [
  {
    target: "context-engine",
    title: "Context Engine",
    body: "Why your stocks moved today — and what to watch tomorrow. Run this every morning before market open.",
  },
  {
    target: "news-feed",
    title: "News Impact Feed",
    body: "Every headline tagged with your stake. We tell you which of YOUR holdings each story touches and in which direction.",
  },
  {
    target: "ai-analysis-cta",
    title: "AI Analysis",
    body: "Click Run AI Analysis for bull/bear/watch thesis on your top holdings — the decision aid no other Indian retail app has.",
  },
];

function shouldShow() {
  if (typeof window === "undefined") return false;
  try {
    return !localStorage.getItem(STORAGE_KEY);
  } catch {
    return true;
  }
}

function markSeen() {
  try { localStorage.setItem(STORAGE_KEY, "seen"); } catch {}
}

export default function OnboardingTour({ trigger = 0 }) {
  const [active, setActive] = useState(false);
  const [stepIdx, setStepIdx] = useState(0);
  // Bounding-rect of the current step's target element so the callout
  // can position itself near (but not over) the actual feature.
  const [anchorRect, setAnchorRect] = useState(null);

  // Decide whether to mount the tour. Triggered when `trigger` prop bumps
  // (i.e. immediately after onboarding completes) — also evaluated on
  // initial mount in case a returning new user lands directly.
  useEffect(() => {
    if (!shouldShow()) return;
    // Give the dashboard one frame to render its first cards before
    // we start hunting for [data-tour] anchors. Without this delay the
    // Context Engine card may not exist yet.
    const t = setTimeout(() => setActive(true), 600);
    return () => clearTimeout(t);
  }, [trigger]);

  const dismiss = useCallback(() => {
    markSeen();
    setActive(false);
  }, []);

  const next = useCallback(() => {
    if (stepIdx + 1 >= STEPS.length) {
      dismiss();
      return;
    }
    setStepIdx((i) => i + 1);
  }, [stepIdx, dismiss]);

  // Re-measure the current step's anchor whenever step changes, on
  // resize, and on scroll. Skip the step entirely if the anchor isn't
  // in the DOM (e.g. user is on a tab where it doesn't render).
  useLayoutEffect(() => {
    if (!active) return;
    const measure = () => {
      const step = STEPS[stepIdx];
      if (!step) { dismiss(); return; }
      const el = document.querySelector(`[data-tour="${step.target}"]`);
      if (!el) {
        // Auto-skip steps whose anchor isn't visible — don't block the
        // tour just because the user navigated away from the dashboard.
        if (stepIdx + 1 < STEPS.length) {
          setStepIdx((i) => i + 1);
        } else {
          dismiss();
        }
        return;
      }
      setAnchorRect(el.getBoundingClientRect());
    };
    measure();
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, { passive: true });
    return () => {
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure);
    };
  }, [active, stepIdx, dismiss]);

  // ESC dismisses.
  useEffect(() => {
    if (!active) return;
    const onKey = (e) => { if (e.key === "Escape") dismiss(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, dismiss]);

  if (!active || !anchorRect) return null;

  const step = STEPS[stepIdx];
  // Position the callout: prefer below the anchor, fall back to above
  // if there isn't enough viewport room below.
  const calloutWidth = 320;
  const viewportW = typeof window !== "undefined" ? window.innerWidth : 1200;
  const viewportH = typeof window !== "undefined" ? window.innerHeight : 800;
  const spaceBelow = viewportH - anchorRect.bottom;
  const placeBelow = spaceBelow > 220 || anchorRect.top < 200;
  const top = placeBelow ? anchorRect.bottom + 12 : anchorRect.top - 12;
  let left = anchorRect.left + anchorRect.width / 2 - calloutWidth / 2;
  // Keep callout inside viewport gutters.
  const margin = 16;
  left = Math.max(margin, Math.min(viewportW - calloutWidth - margin, left));

  return (
    <>
      {/* Anchor outline + soft cutout. Pure CSS box-shadow trick to dim
          the rest of the screen WITHOUT a fullscreen overlay (so the
          dashboard remains visible + interactive after the tour ends). */}
      <div
        aria-hidden
        style={{
          position: "fixed",
          left: anchorRect.left - 6,
          top: anchorRect.top - 6,
          width: anchorRect.width + 12,
          height: anchorRect.height + 12,
          borderRadius: "12px",
          border: "1.5px solid var(--color-accent-primary)",
          boxShadow:
            "0 0 0 9999px rgba(0,0,0,0.55), 0 0 30px rgba(99,102,241,0.35)",
          pointerEvents: "none",
          zIndex: 1200,
          transition: "all 0.32s cubic-bezier(0.16, 1, 0.3, 1)",
          animation: "tour-pulse 2.4s ease-in-out infinite",
        }}
      />

      {/* The callout card itself */}
      <div
        role="dialog"
        aria-modal="false"
        style={{
          position: "fixed",
          top,
          left,
          width: calloutWidth,
          background: "var(--color-bg-card)",
          border: "1px solid var(--border-strong)",
          borderRadius: "var(--radius-card, 12px)",
          padding: "18px 20px 16px",
          boxShadow: "var(--shadow-pop)",
          zIndex: 1201,
          fontFamily: "var(--font-inter, 'Inter', system-ui, sans-serif)",
          animation: "tour-rise 0.28s cubic-bezier(0.16, 1, 0.3, 1) both",
          transform: placeBelow ? "translateY(0)" : "translateY(-100%)",
        }}
      >
        {/* Step indicator */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: "10px",
          }}
        >
          <span
            style={{
              fontSize: "9.5px",
              fontWeight: 700,
              letterSpacing: "0.18em",
              color: "var(--color-accent-primary)",
              fontFamily: "var(--font-mono, ui-monospace, monospace)",
            }}
          >
            STEP {stepIdx + 1} / {STEPS.length}
          </span>
          <button
            type="button"
            onClick={dismiss}
            style={{
              padding: "2px 6px",
              fontSize: "10px",
              fontWeight: 600,
              letterSpacing: "0.06em",
              border: "none",
              background: "transparent",
              color: "var(--color-text-muted)",
              cursor: "pointer",
              fontFamily: "var(--font-mono, ui-monospace, monospace)",
            }}
          >
            SKIP TOUR
          </button>
        </div>

        {/* Title */}
        <h3
          style={{
            fontSize: "15px",
            fontWeight: 700,
            color: "var(--color-text-primary)",
            letterSpacing: "-0.01em",
            marginBottom: "6px",
          }}
        >
          {step.title}
        </h3>

        {/* Body */}
        <p
          style={{
            fontSize: "12.5px",
            color: "var(--color-text-secondary)",
            lineHeight: 1.55,
            marginBottom: "14px",
          }}
        >
          {step.body}
        </p>

        {/* Action row */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "flex-end",
            gap: "10px",
          }}
        >
          {/* Step dots */}
          <div style={{ display: "flex", gap: "5px", marginRight: "auto" }}>
            {STEPS.map((_, i) => (
              <span
                key={i}
                style={{
                  width: i === stepIdx ? "16px" : "5px",
                  height: "5px",
                  borderRadius: "999px",
                  background: i === stepIdx
                    ? "var(--color-accent-primary)"
                    : "var(--border-strong)",
                  transition: "width 0.2s",
                }}
              />
            ))}
          </div>
          <button
            type="button"
            onClick={next}
            style={{
              padding: "8px 16px",
              borderRadius: "var(--radius-control, 8px)",
              border: "1px solid var(--color-accent-primary)",
              background: "var(--color-accent-primary)",
              color: "#fff",
              fontSize: "12px",
              fontWeight: 700,
              letterSpacing: "0.02em",
              cursor: "pointer",
              transition: "filter 0.15s",
            }}
            onMouseEnter={(e) => { e.currentTarget.style.filter = "brightness(1.12)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.filter = "none"; }}
          >
            {stepIdx + 1 === STEPS.length ? "Got it" : "Next →"}
          </button>
        </div>
      </div>

      {/* Both keyframes live here — single global style tag avoids the
          "nested <style jsx>" parse error from Turbopack. */}
      <style jsx global>{`
        @keyframes tour-rise {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes tour-pulse {
          0%, 100% { box-shadow: 0 0 0 9999px rgba(0,0,0,0.55), 0 0 30px rgba(99,102,241,0.35); }
          50%      { box-shadow: 0 0 0 9999px rgba(0,0,0,0.55), 0 0 50px rgba(99,102,241,0.55); }
        }
      `}</style>
    </>
  );
}
