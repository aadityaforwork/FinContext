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

  // Decide whether to mount the tour. Triggered when `trigger` prop bumps
  // (i.e. immediately after the FirstInsightCard dismisses). The dashboard
  // beneath us has already rendered (we reloaded BEFORE the card opened),
  // but we still wait 400ms so the user's eye has time to land on the
  // dashboard before the spotlight pulls focus to one widget.
  useEffect(() => {
    if (!shouldShow(userId)) return;
    const t = setTimeout(() => setActive(true), 400);
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
  // Mobile bottom navbar is 60px high on phones (see Sidebar.jsx). Reserve
  // a 76px safe-zone at the bottom of the viewport so the callout never
  // overlaps the nav — that's a major mobile usability papercut.
  const bottomReserved = viewportW < 768 ? 76 : 16;
  // Responsive callout width: shrink to fit phones, cap at 320 on desktop.
  // 32px total horizontal margin (16px each side).
  const calloutWidth = Math.min(320, viewportW - 32);
  const margin = 16;
  const spaceBelow = viewportH - bottomReserved - anchorRect.bottom;
  // Estimate callout height ~ 200 (3 short paragraphs + buttons). If we
  // can't fit it below AND can't fit it above, prefer above and let the
  // scrollIntoView in the measure effect handle anchor placement.
  const placeBelow = spaceBelow > 220 || anchorRect.top < 220;
  let top = placeBelow ? anchorRect.bottom + 12 : anchorRect.top - 12;
  let left = anchorRect.left + anchorRect.width / 2 - calloutWidth / 2;
  // Clamp horizontally so the callout never escapes the viewport gutters.
  left = Math.max(margin, Math.min(viewportW - calloutWidth - margin, left));
  // Clamp vertically too — don't run under the mobile bottom navbar.
  if (placeBelow) {
    top = Math.min(top, viewportH - bottomReserved - 220);
  } else {
    top = Math.max(margin, top);
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
