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

// Per-user storage key — see OnboardingModal for the cross-account bug
// this fixes.
const STORAGE_KEY_BASE = "fincontext_tour_seen_v2";
const keyFor = (userId) => `${STORAGE_KEY_BASE}_${userId || "anon"}`;

// Steps in display order. Each step has a list of `targets` matched
// against [data-tour] attributes — the FIRST one that exists in the DOM
// wins. That matters because a freshly-onboarded user only has a
// watchlist (no portfolio) → PortfolioTodayStrip returns null → we fall
// back to UniverseRail. A user who already has a portfolio sees the
// stronger anchor. Either way they always get 3 steps, not 2.
//
// The old single-`target` design caused "step 1 never shows, jumps to
// step 2" — the target (`context-engine`) lived on a screen the user
// wasn't on, so auto-skip swallowed step 1 silently.
const STEPS = [
  {
    targets: ["portfolio-today", "universe-rail"],
    title: "Your picks, live",
    body: "Every stock you added is tracked here in real time — P&L if you set buy prices, day change otherwise.",
  },
  {
    targets: ["news-feed"],
    title: "News tagged with your stake",
    body: "Every headline shows which of YOUR picks it touches and in which direction. The personalization no other Indian app does.",
  },
  {
    targets: ["ai-analysis-cta", "universe-rail"],
    title: "Run AI Analysis when ready",
    body: "Click Run AI Analysis on the strip above for bull / bear / watch thesis on your top holdings. Powered by your portfolio's actual data.",
  },
];

/** Find the first data-tour anchor that exists for this step's targets. */
function resolveAnchor(step) {
  for (const t of step.targets || []) {
    const el = document.querySelector(`[data-tour="${t}"]`);
    if (el) return el;
  }
  return null;
}

function shouldShow(userId) {
  if (typeof window === "undefined") return false;
  try {
    return !localStorage.getItem(keyFor(userId));
  } catch {
    return true;
  }
}

function markSeen(userId) {
  try { localStorage.setItem(keyFor(userId), "seen"); } catch {}
}

export default function OnboardingTour({ trigger = 0, userId }) {
  const [active, setActive] = useState(false);
  const [stepIdx, setStepIdx] = useState(0);
  // Bounding-rect of the current step's target element so the callout
  // can position itself near (but not over) the actual feature.
  const [anchorRect, setAnchorRect] = useState(null);

  // The tour fires ONLY when `trigger` bumps to a non-zero value. Previously
  // it also fired on plain mount whenever shouldShow() was true — which is
  // ALWAYS true for a brand-new user, so the tour started while the wizard
  // modal was still open (overlapping the spotlight ring with the modal
  // backdrop). This was the "tour appears over the wizard" bug in the
  // screenshot.
  //
  // Now: page.js bumps trigger when (a) FirstInsightCard dismisses, or
  // (b) URL has ?tour=1 (Settings → Replay tour). On plain page load with
  // no trigger, the tour stays dormant.
  //
  // Delay is 800ms (was 400) — gives the dashboard a generous render
  // window so anchor elements like UniverseRail are mounted by the time
  // measure() runs querySelector.
  useEffect(() => {
    if (trigger === 0) return;
    if (!shouldShow(userId)) return;
    const t = setTimeout(() => setActive(true), 800);
    return () => clearTimeout(t);
  }, [trigger, userId]);

  const dismiss = useCallback(() => {
    markSeen(userId);
    setActive(false);
  }, [userId]);

  const next = useCallback(() => {
    if (stepIdx + 1 >= STEPS.length) {
      dismiss();
      return;
    }
    setStepIdx((i) => i + 1);
  }, [stepIdx, dismiss]);

  // Re-measure the current step's anchor whenever step changes, on resize,
  // on scroll. Two extra concerns from the mobile bug report:
  //
  //   1. The anchor element might be below the fold (especially on phones
  //      where every section is taller). On step change, scroll the anchor
  //      into view ONCE so the callout has something to pin to.
  //   2. The mobile sidebar lives at the bottom of the viewport; the tour
  //      shouldn't pulse on the very last screen pixel under it. The
  //      callout positioning logic below already prefers above/below the
  //      anchor with viewport-aware clamping.
  useLayoutEffect(() => {
    if (!active) return;
    let scrolledThisStep = false;
    const measure = () => {
      const step = STEPS[stepIdx];
      if (!step) { dismiss(); return; }
      const el = resolveAnchor(step);
      if (!el) {
        // Tried every fallback target for this step and none are in the
        // DOM. Skip rather than block — but with the new fallbacks this
        // should be extremely rare (universe-rail is always rendered).
        if (stepIdx + 1 < STEPS.length) {
          setStepIdx((i) => i + 1);
        } else {
          dismiss();
        }
        return;
      }
      const rect = el.getBoundingClientRect();
      const vh = window.innerHeight;
      // If anchor is off-screen (above or below), scroll it gently into
      // the middle of the viewport — ONCE per step.
      if (!scrolledThisStep && (rect.top < 60 || rect.bottom > vh - 60)) {
        scrolledThisStep = true;
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        // Re-measure after the scroll animation roughly settles.
        setTimeout(measure, 360);
        return;
      }
      setAnchorRect(rect);
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
  const viewportW = typeof window !== "undefined" ? window.innerWidth : 1200;
  const viewportH = typeof window !== "undefined" ? window.innerHeight : 800;
  const isMobile = viewportW < 768;

  // MOBILE: position via `bottom` + `left` + `right` directly. That bypasses
  // every mobile-browser-chrome edge case (address bar resizing the visible
  // viewport, soft keyboard pushing things up, viewportH lying about visible
  // area). No `top`, no `translateY` arithmetic — just "stick to the bottom,
  // span the width, leave room for the bottom nav."
  //
  // DESKTOP: anchor-relative positioning so the callout feels tightly
  // connected to what it's pointing at.
  const margin = 16;
  let calloutStyle;
  if (isMobile) {
    // Mobile bottom navbar is 60px (Sidebar.jsx) + 16 of breathing room = 76.
    calloutStyle = {
      position: "fixed",
      bottom: 76,
      left: margin,
      right: margin,
      // `maxHeight + overflow` so a long step body can scroll inside the
      // callout rather than escape the viewport. Keeps the action row
      // (Next button) reachable even with the smallest screens.
      maxHeight: Math.min(360, viewportH - 76 - 32),
      overflowY: "auto",
    };
  } else {
    const calloutWidth = 320;
    const spaceBelow = viewportH - 16 - anchorRect.bottom;
    const placeBelow = spaceBelow > 220 || anchorRect.top < 220;
    let calloutTop = placeBelow ? anchorRect.bottom + 12 : anchorRect.top - 12;
    let calloutLeft = anchorRect.left + anchorRect.width / 2 - calloutWidth / 2;
    calloutLeft = Math.max(margin, Math.min(viewportW - calloutWidth - margin, calloutLeft));
    if (placeBelow) {
      calloutTop = Math.min(calloutTop, viewportH - 16 - 220);
    } else {
      calloutTop = Math.max(margin, calloutTop);
    }
    calloutStyle = {
      position: "fixed",
      top: calloutTop,
      left: calloutLeft,
      width: calloutWidth,
      transform: placeBelow ? "translateY(0)" : "translateY(-100%)",
    };
  }

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
          ...calloutStyle,
          background: "var(--color-bg-card)",
          border: "1px solid var(--border-strong)",
          borderRadius: "var(--radius-card, 12px)",
          padding: "18px 20px 16px",
          boxShadow: "var(--shadow-pop)",
          zIndex: 1201,
          fontFamily: "var(--font-sans)",
          animation: "tour-rise 0.28s cubic-bezier(0.16, 1, 0.3, 1) both",
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
              fontFamily: "var(--font-mono)",
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
              fontFamily: "var(--font-mono)",
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
