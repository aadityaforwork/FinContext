"use client";

/**
 * FirstInsightCard — Act 2 of the "First Five Minutes" onboarding.
 *
 * Shows AFTER the OnboardingModal completes, BEFORE the dashboard loads.
 * Single full-screen card with ONE personalized insight pulled from
 * /api/onboarding/first-insight. The whole purpose is the dopamine hit:
 * the user just typed 4 ticker symbols and now sees a sentence like
 *
 *   "HDFC Bank reports earnings tomorrow — you're already tracking it."
 *
 * That's the moment they say "oh, this thing actually knows my stuff."
 *
 * Visual: matches the editorial-quiet NewsWireLoader (large serif headline,
 * hairline rules, restraint). Two actions: primary "Open dashboard" CTA,
 * skip link below. Auto-dismissable by clicking outside the card.
 *
 * One-shot: a localStorage flag prevents re-showing this card on later
 * sessions — it's a first-visit-only surface.
 */

import { useEffect, useState } from "react";
import { API_BASE } from "../lib/api";

// Per-user storage key — see the same fix in OnboardingModal for the
// reasoning. Without per-user scoping, a second account on the same
// browser would never see the FirstInsightCard.
const STORAGE_KEY_BASE = "fincontext_first_insight_seen_v2";
const keyFor = (userId) => `${STORAGE_KEY_BASE}_${userId || "anon"}`;

export function shouldShowFirstInsight(userId) {
  if (typeof window === "undefined") return false;
  try {
    return !localStorage.getItem(keyFor(userId));
  } catch {
    return true;
  }
}

export default function FirstInsightCard({ open, tickers = [], userId, onDismiss }) {
  const [insight, setInsight] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  // Fetch on open. Set the "seen" flag immediately so a refresh during this
  // moment doesn't re-show the card forever.
  useEffect(() => {
    if (!open) return;
    try { localStorage.setItem(keyFor(userId), "shown"); } catch {}
    setLoading(true);
    setError(false);
    const ctrl = new AbortController();
    fetch(`${API_BASE}/api/onboarding/first-insight`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tickers }),
      signal: ctrl.signal,
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data) => { setInsight(data); setLoading(false); })
      .catch((err) => {
        if (err.name === "AbortError") return;
        setError(true);
        setLoading(false);
      });
    return () => ctrl.abort();
  }, [open, tickers, userId]);

  // ESC dismisses.
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape") onDismiss?.(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onDismiss]);

  if (!open) return null;

  // Pick label/color for the small "kind" badge at the top of the card.
  const kindBadge = (() => {
    const k = insight?.kind;
    if (k === "earnings") return { label: "EARNINGS ALERT", color: "var(--color-accent-amber)" };
    if (k === "mover")    return { label: "BIG MOVER",      color: "var(--color-accent-primary)" };
    if (k === "policy")   return { label: "POLICY MATCH",   color: "var(--color-accent-cyan)" };
    if (k === "concentration") return { label: "PORTFOLIO INSIGHT", color: "var(--color-accent-primary)" };
    return { label: "WELCOME", color: "var(--color-accent-primary)" };
  })();

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={(e) => { if (e.target === e.currentTarget) onDismiss?.(); }}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.78)",
        backdropFilter: "blur(10px)",
        WebkitBackdropFilter: "blur(10px)",
        zIndex: 1100,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px",
        animation: "fic-fade 0.25s ease-out",
      }}
    >
      <style>{`
        @keyframes fic-fade { from { opacity: 0 } to { opacity: 1 } }
        @keyframes fic-rise { from { transform: translateY(16px); opacity: 0 } to { transform: translateY(0); opacity: 1 } }
        @keyframes fic-bar {
          from { width: 0; opacity: 0.6 }
          to   { width: 100%; opacity: 1 }
        }
      `}</style>

      <article
        style={{
          width: "min(640px, 100%)",
          background: "var(--color-bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-card, 12px)",
          padding: "44px 40px 36px",
          display: "flex",
          flexDirection: "column",
          gap: "28px",
          animation: "fic-rise 0.32s cubic-bezier(0.16, 1, 0.3, 1) both",
        }}
      >
        {/* Kind badge — single small mono label at top */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "9px" }}>
            <span
              style={{
                width: "7px",
                height: "7px",
                borderRadius: "50%",
                background: kindBadge.color,
                boxShadow: `0 0 6px ${kindBadge.color}88`,
              }}
            />
            <span
              style={{
                fontSize: "10px",
                fontWeight: 700,
                letterSpacing: "0.18em",
                color: kindBadge.color,
                fontFamily: "var(--font-mono)",
              }}
            >
              {loading ? "READING YOUR PICKS…" : kindBadge.label}
            </span>
          </div>
          <span
            style={{
              fontSize: "10px",
              fontWeight: 700,
              letterSpacing: "0.14em",
              color: "var(--color-text-muted)",
              fontFamily: "var(--font-mono)",
            }}
          >
            YOUR FIRST INSIGHT
          </span>
        </div>

        {/* Hairline — thin animated bar to mark loading */}
        <div
          style={{
            height: "1px",
            background:
              "linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.14) 50%, transparent 100%)",
          }}
        />

        {/* Main content area */}
        <div style={{ display: "flex", flexDirection: "column", gap: "18px", minHeight: "120px" }}>
          {loading ? (
            <LoadingBars />
          ) : error || !insight ? (
            <>
              <h2
                style={{
                  fontFamily: "var(--font-serif)",
                  fontSize: "26px",
                  fontWeight: 400,
                  fontStyle: "italic",
                  color: "var(--color-text-primary)",
                  lineHeight: 1.35,
                  letterSpacing: "-0.01em",
                  margin: 0,
                }}
              >
                Your dashboard is ready.
              </h2>
              <p style={{ fontSize: "14px", color: "var(--color-text-secondary)", lineHeight: 1.6, margin: 0 }}>
                We&apos;ll surface news, earnings, and policy events on your picks the moment you open it.
              </p>
            </>
          ) : (
            <>
              <h2
                style={{
                  fontFamily: "var(--font-serif)",
                  fontSize: "28px",
                  fontWeight: 400,
                  color: "var(--color-text-primary)",
                  lineHeight: 1.3,
                  letterSpacing: "-0.012em",
                  margin: 0,
                }}
              >
                {insight.ticker ? (
                  <>
                    <span
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: "20px",
                        fontWeight: 700,
                        background: "var(--color-bg-card-hover)",
                        border: "1px solid var(--border-strong)",
                        padding: "3px 9px",
                        borderRadius: "5px",
                        marginRight: "10px",
                        verticalAlign: "middle",
                        letterSpacing: "-0.01em",
                      }}
                    >
                      {insight.ticker}
                    </span>
                    <span style={{ fontStyle: "italic" }}>{insight.headline}</span>
                  </>
                ) : (
                  <span style={{ fontStyle: "italic" }}>{insight.headline}</span>
                )}
              </h2>
              <p
                style={{
                  fontSize: "14.5px",
                  color: "var(--color-text-secondary)",
                  lineHeight: 1.65,
                  letterSpacing: "-0.003em",
                  margin: 0,
                }}
              >
                {insight.body}
              </p>
            </>
          )}
        </div>

        {/* Bottom hairline */}
        <div
          style={{
            height: "1px",
            background:
              "linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.10) 50%, transparent 100%)",
          }}
        />

        {/* Actions */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "16px",
          }}
        >
          <button
            type="button"
            onClick={onDismiss}
            style={{
              padding: "6px 4px",
              background: "transparent",
              border: "none",
              color: "var(--color-text-muted)",
              fontSize: "12px",
              fontWeight: 600,
              letterSpacing: "0.06em",
              cursor: "pointer",
            }}
          >
            Skip
          </button>
          <button
            type="button"
            onClick={onDismiss}
            disabled={loading}
            style={{
              padding: "11px 26px",
              borderRadius: "var(--radius-control, 8px)",
              border: "1px solid var(--color-accent-primary)",
              background: loading ? "var(--color-bg-card-hover)" : "var(--color-accent-primary)",
              color: loading ? "var(--color-text-muted)" : "#fff",
              fontSize: "13px",
              fontWeight: 700,
              letterSpacing: "0.02em",
              cursor: loading ? "wait" : "pointer",
              transition: "filter 0.15s",
            }}
            onMouseEnter={(e) => { if (!loading) e.currentTarget.style.filter = "brightness(1.12)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.filter = "none"; }}
          >
            {insight?.cta?.label || "Open dashboard"} &nbsp;→
          </button>
        </div>
      </article>
    </div>
  );
}

// Three thin loading bars that animate from 0 → 100% width. Replaces a
// spinner — feels intentional, not "spinner go brrr".
function LoadingBars() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "10px", paddingTop: "8px" }}>
      <Bar w="68%" delay="0s" />
      <Bar w="86%" delay="0.18s" />
      <Bar w="52%" delay="0.36s" />
    </div>
  );
}

function Bar({ w = "70%", delay = "0s" }) {
  return (
    <div
      style={{
        height: "10px",
        borderRadius: "3px",
        background: "rgba(255,255,255,0.05)",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          height: "100%",
          width: w,
          background:
            "linear-gradient(90deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0.12) 50%, rgba(255,255,255,0.04) 100%)",
          backgroundSize: "200% 100%",
          animation: `wire-shimmer-slide 2s linear infinite, fic-bar-grow 0.9s cubic-bezier(0.16,1,0.3,1) ${delay} both`,
        }}
      />
      <style jsx>{`
        @keyframes wire-shimmer-slide { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
        @keyframes fic-bar-grow { from { width: 0; opacity: 0; } to { opacity: 1; } }
      `}</style>
    </div>
  );
}
