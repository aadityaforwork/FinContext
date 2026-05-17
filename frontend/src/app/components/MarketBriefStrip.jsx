"use client";

/**
 * MarketBriefStrip
 * ----------------
 * Two surfaces:
 *   1. The dashboard strip — one quiet line + headline + "Open brief" CTA.
 *   2. The drawer ("Editorial brief") — the unique part. Instead of a vertical
 *      scroll of paragraphs with emoji headers, it now feels like opening a
 *      morning newspaper:
 *
 *        ─── 17 MAY · 07:42 IST ─────────────────────
 *
 *            "Index drifts higher, but your IT
 *             cluster carries most of the upside."
 *
 *            6 SECTIONS · ~2 MIN · MEDIUM CONFIDENCE
 *
 *        ─── CONTENTS ───────────────────────────────
 *        01 ▸ Overnight                     tailwind
 *        02 ▸ India open                    tailwind
 *        ...
 *
 *        Each section then renders as its own card with:
 *           – mono section number, name in caps, stance tag
 *           – stance accent ribbon (3px) at the card top
 *           – serif body for comfortable reading
 *           – ticker chips inline
 *           – right-side floating dot-rail for jumping
 *
 * Everything aligns with the editorial-quiet language used across the rest of
 * the product. No emojis, no gradients, single indigo accent, mono labels.
 */

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { supabase } from "../lib/supabase";
import { API_BASE } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Spinner } from "./Loaders";

const SERIF = "var(--font-serif)";
const MONO  = "var(--font-mono)";

const STANCE_COLOR = {
  tailwind: "var(--color-accent-green)",
  headwind: "var(--color-accent-red)",
  mixed:    "var(--color-accent-amber)",
  neutral:  "var(--color-text-muted)",
};

const STANCE_LABEL = {
  tailwind: "TAILWIND",
  headwind: "HEADWIND",
  mixed:    "MIXED",
  neutral:  "NEUTRAL",
};

// ---------------------------------------------------------------------------
// Format helpers
// ---------------------------------------------------------------------------
function formatDateIST(iso) {
  // Format generated_at as "17 MAY · 07:42 IST" so the cover feels like a
  // dated edition (newspaper masthead vibe).
  try {
    const d = new Date(iso);
    const day = d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", timeZone: "Asia/Kolkata" }).toUpperCase().replace(".", "");
    const time = d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Kolkata" });
    return `${day} · ${time} IST`;
  } catch {
    return "TODAY";
  }
}

function estimateReadMinutes(sections) {
  // ~220 words per minute, minimum 1 min.
  const words = (sections || []).reduce((acc, s) => acc + (s.body || "").split(/\s+/).length, 0);
  const mins = Math.max(1, Math.round(words / 220));
  return mins;
}

// ---------------------------------------------------------------------------
// Trigger strip — unchanged behaviour, slightly cleaner styling.
// ---------------------------------------------------------------------------
export default function MarketBriefStrip({ onNavigate }) {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(false);
  const drawerRef = useRef(null);

  const fetchSummary = useCallback(async (force = false) => {
    if (!user?.id) return;
    if (force) setRefreshing(true); else setLoading(true);
    try {
      const [{ data: positions }, { data: watchRows }] = await Promise.all([
        supabase.from("portfolio").select("ticker, quantity, buy_price").eq("user_id", user.id),
        supabase.from("watchlist").select("ticker").eq("user_id", user.id),
      ]);
      const res = await fetch(`${API_BASE}/api/intelligence/market-summary`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          positions: positions || [],
          watchlist_tickers: (watchRows || []).map((r) => r.ticker),
          force_refresh: force,
        }),
      });
      if (res.ok) setData(await res.json());
    } catch { /* drawer shows error state */ }
    finally { setLoading(false); setRefreshing(false); }
  }, [user?.id]);

  useEffect(() => { fetchSummary(false); }, [fetchSummary]);

  // Close drawer on Escape
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const headline = data?.headline || (loading ? "Drafting today's market view…" : "Today's market summary");

  return (
    <>
      {/* TRIGGER STRIP */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        disabled={loading && !data}
        className="dash-strip dash-brief-strip"
        aria-label="Open today's editorial market brief"
        style={{
          width: "100%",
          padding: "12px 20px",
          borderRadius: "12px",
          background: "var(--color-bg-card)",
          border: "1px solid var(--border-subtle)",
          display: "flex",
          alignItems: "center",
          gap: "14px",
          textAlign: "left",
          cursor: loading && !data ? "wait" : "pointer",
          transition: "border-color 0.15s, background 0.15s",
        }}
        onMouseEnter={(e) => {
          if (!loading || data) {
            e.currentTarget.style.borderColor = "rgba(99,102,241,0.30)";
            e.currentTarget.style.background = "rgba(99,102,241,0.04)";
          }
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.borderColor = "var(--border-subtle)";
          e.currentTarget.style.background = "var(--color-bg-card)";
        }}
      >
        <span
          className="dbs-label"
          style={{
            fontSize: "9px",
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: "0.14em",
            color: "var(--color-text-muted)",
            flexShrink: 0,
            fontFamily: MONO,
          }}
        >
          Today's brief
        </span>
        <span
          className="dbs-sep"
          style={{ width: "1px", height: "14px", background: "var(--border-subtle)", flexShrink: 0 }}
        />
        {loading && !data ? (
          <span style={{ display: "flex", alignItems: "center", gap: "8px", flex: 1 }}>
            <Spinner size="sm" />
            <span style={{ fontSize: "12px", color: "var(--color-text-muted)" }}>{headline}</span>
          </span>
        ) : (
          <span
            className="dbs-headline"
            style={{
              fontSize: "13px",
              fontWeight: 500,
              color: "var(--color-text-secondary)",
              fontFamily: SERIF,
              fontStyle: "italic",
              flex: 1,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              letterSpacing: "-0.003em",
            }}
          >
            &ldquo;{headline}&rdquo;
          </span>
        )}
        <span
          className="dbs-cta"
          style={{
            fontSize: "10.5px",
            fontWeight: 700,
            color: "var(--color-accent-primary)",
            letterSpacing: "0.08em",
            flexShrink: 0,
            fontFamily: MONO,
            textTransform: "uppercase",
          }}
        >
          Read →
        </span>
      </button>

      {/* DRAWER */}
      {open && (
        <BriefDrawer
          data={data}
          refreshing={refreshing}
          onRefresh={() => fetchSummary(true)}
          onClose={() => setOpen(false)}
          onNavigate={onNavigate}
          drawerRef={drawerRef}
        />
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Drawer — the editorial brief
// ---------------------------------------------------------------------------
function BriefDrawer({ data, refreshing, onRefresh, onClose, onNavigate, drawerRef }) {
  const [activeIdx, setActiveIdx] = useState(0);
  const sectionRefs = useRef([]);
  const contentRef = useRef(null);

  const sections = data?.sections || [];
  const dateStr = formatDateIST(data?.generated_at || new Date().toISOString());
  const readMin = estimateReadMinutes(sections);

  // Stance distribution — used in the cover stats row.
  const stanceCounts = useMemo(() => {
    const acc = { tailwind: 0, headwind: 0, mixed: 0, neutral: 0 };
    sections.forEach((s) => { acc[s.stance || "neutral"] = (acc[s.stance || "neutral"] || 0) + 1; });
    return acc;
  }, [sections]);

  // IntersectionObserver — light up the active dot on the right rail as the
  // reader scrolls. Threshold is set high enough that the active card has to
  // dominate the viewport before we switch — avoids flicker on small cards.
  useEffect(() => {
    if (!sections.length) return;
    const root = contentRef.current;
    if (!root) return;
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            const idx = Number(e.target.getAttribute("data-section-idx"));
            if (!Number.isNaN(idx)) setActiveIdx(idx);
          }
        });
      },
      { root, threshold: 0.5 }
    );
    sectionRefs.current.forEach((el) => el && io.observe(el));
    return () => io.disconnect();
  }, [sections.length]);

  const jumpTo = (idx) => {
    const el = sectionRefs.current[idx];
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(8,11,18,0.72)",
        backdropFilter: "blur(6px)",
        WebkitBackdropFilter: "blur(6px)",
        zIndex: 1000,
        display: "flex",
        justifyContent: "flex-end",
        animation: "mb-fade-in 0.22s ease-out",
      }}
    >
      <style>{`
        @keyframes mb-fade-in { from { opacity: 0 } to { opacity: 1 } }
        @keyframes mb-slide-in { from { transform: translateX(40px); opacity: 0 } to { transform: translateX(0); opacity: 1 } }
        @keyframes mb-hero-in { from { opacity: 0; transform: translateY(6px) } to { opacity: 1; transform: translateY(0) } }
      `}</style>

      <div
        ref={drawerRef}
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "min(640px, 96vw)",
          height: "100vh",
          background: "var(--color-bg-primary)",
          borderLeft: "1px solid var(--border-subtle)",
          display: "flex",
          flexDirection: "column",
          boxShadow: "-12px 0 40px rgba(0,0,0,0.5)",
          animation: "mb-slide-in 0.24s ease-out",
          position: "relative",
        }}
      >
        {/* Top-right action cluster — kept floating so the cover reads clean. */}
        <div
          style={{
            position: "absolute",
            top: "14px",
            right: "16px",
            display: "flex",
            gap: "6px",
            zIndex: 10,
          }}
        >
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing}
            aria-label="Refresh brief"
            style={{
              padding: "6px 10px",
              borderRadius: "var(--radius-control)",
              border: "1px solid var(--border-subtle)",
              background: "var(--color-bg-card)",
              color: "var(--color-text-muted)",
              fontSize: "11px",
              fontWeight: 700,
              cursor: refreshing ? "wait" : "pointer",
              opacity: refreshing ? 0.6 : 1,
              fontFamily: MONO,
            }}
          >
            {refreshing ? <Spinner size="sm" /> : "↻"}
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close brief"
            style={{
              width: "30px",
              height: "30px",
              borderRadius: "var(--radius-control)",
              border: "1px solid var(--border-subtle)",
              background: "var(--color-bg-card)",
              color: "var(--color-text-secondary)",
              cursor: "pointer",
              fontSize: "18px",
              lineHeight: 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            ×
          </button>
        </div>

        {/* Scrollable content */}
        <div
          ref={contentRef}
          style={{
            flex: 1,
            overflowY: "auto",
            padding: "0",
          }}
        >
          {/* ─────── COVER ─────── */}
          {data ? (
            <CoverPage
              dateStr={dateStr}
              headline={data.headline}
              readMin={readMin}
              confidence={data.confidence}
              sectionCount={sections.length}
              stanceCounts={stanceCounts}
              demoMode={data.demo_mode}
            />
          ) : (
            <div style={{ padding: "80px 28px", textAlign: "center", color: "var(--color-text-muted)" }}>
              <Spinner size="sm" />
              <p style={{ marginTop: "12px", fontSize: "13px" }}>Loading today&rsquo;s brief…</p>
            </div>
          )}

          {/* ─────── TABLE OF CONTENTS ─────── */}
          {sections.length > 0 && (
            <TableOfContents sections={sections} onJump={jumpTo} />
          )}

          {/* ─────── SECTION CARDS ─────── */}
          {sections.length > 0 && (
            <div style={{ padding: "0 28px 32px" }}>
              {sections.map((sec, idx) => (
                <div
                  key={idx}
                  data-section-idx={idx}
                  ref={(el) => (sectionRefs.current[idx] = el)}
                  style={{ marginBottom: "20px", scrollMarginTop: "24px" }}
                >
                  <SectionCard
                    index={idx}
                    section={sec}
                    onTickerClick={(t) => { onClose(); onNavigate?.("company", t); }}
                  />
                </div>
              ))}
            </div>
          )}

          {/* Empty / error */}
          {data && sections.length === 0 && (
            <div style={{ padding: "60px 28px", textAlign: "center", color: "var(--color-text-muted)", fontSize: "13px" }}>
              {data?.error || "Brief unavailable right now."}
            </div>
          )}

          {/* Disclaimer */}
          {data?.disclaimer_short && (
            <p
              style={{
                fontSize: "10px",
                color: "var(--color-text-muted)",
                margin: "24px 28px 32px",
                paddingTop: "16px",
                borderTop: "1px solid var(--border-subtle)",
                textAlign: "center",
                fontStyle: "italic",
                lineHeight: 1.5,
                fontFamily: SERIF,
              }}
            >
              {data.disclaimer_short}
            </p>
          )}
        </div>

        {/* ─────── FLOATING SECTION DOT-RAIL (desktop only) ─────── */}
        {sections.length > 0 && (
          <SectionDotRail
            sections={sections}
            activeIdx={activeIdx}
            onJump={jumpTo}
          />
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Cover page — the masthead. Stillness + a single serif italic headline.
// ---------------------------------------------------------------------------
function CoverPage({ dateStr, headline, readMin, confidence, sectionCount, stanceCounts, demoMode }) {
  return (
    <div
      style={{
        padding: "56px 28px 36px",
        textAlign: "center",
        animation: "mb-hero-in 0.5s ease-out both",
      }}
    >
      {/* Masthead — date + edition */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "12px", marginBottom: "32px" }}>
        <span style={{ width: "min(60px, 18%)", height: "1px", background: "var(--border-subtle)" }} />
        <span
          style={{
            fontFamily: MONO,
            fontSize: "10.5px",
            fontWeight: 700,
            letterSpacing: "0.22em",
            color: "var(--color-text-muted)",
            textTransform: "uppercase",
          }}
        >
          {dateStr}
        </span>
        <span style={{ width: "min(60px, 18%)", height: "1px", background: "var(--border-subtle)" }} />
      </div>

      {/* Headline — serif italic, the hero of the page */}
      <blockquote
        style={{
          margin: "0 auto",
          maxWidth: "440px",
          fontFamily: SERIF,
          fontStyle: "italic",
          fontSize: "23px",
          lineHeight: 1.45,
          color: "var(--color-text-primary)",
          letterSpacing: "-0.008em",
        }}
      >
        &ldquo;{headline || "Today's market view."}&rdquo;
      </blockquote>

      {/* Stats row */}
      <div
        style={{
          marginTop: "32px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: "20px",
          flexWrap: "wrap",
          fontFamily: MONO,
          fontSize: "10.5px",
          fontWeight: 700,
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          color: "var(--color-text-muted)",
        }}
      >
        <span>{sectionCount} sections</span>
        <span style={{ opacity: 0.4 }}>·</span>
        <span>{readMin} min read</span>
        {confidence && (
          <>
            <span style={{ opacity: 0.4 }}>·</span>
            <span title="Confidence in the underlying data behind today's brief">
              {confidence} confidence
            </span>
          </>
        )}
        {demoMode && (
          <>
            <span style={{ opacity: 0.4 }}>·</span>
            <span style={{ color: "var(--color-accent-amber)" }}>sample</span>
          </>
        )}
      </div>

      {/* Stance distribution — tiny visual recap of the day's tone */}
      <StanceStripe counts={stanceCounts} />
    </div>
  );
}

// Stance stripe — proportional bar showing today's tilt. Reads at a glance:
// mostly green = good day for the user, mostly red = rough day.
function StanceStripe({ counts }) {
  const total = (counts.tailwind || 0) + (counts.headwind || 0) + (counts.mixed || 0) + (counts.neutral || 0);
  if (total === 0) return null;
  const seg = (n, color, label) => {
    const pct = (n / total) * 100;
    if (pct === 0) return null;
    return (
      <div
        key={label}
        title={`${n} section${n === 1 ? "" : "s"} · ${label.toLowerCase()}`}
        style={{ width: `${pct}%`, height: "100%", background: color }}
      />
    );
  };
  return (
    <div
      aria-hidden
      style={{
        marginTop: "24px",
        marginInline: "auto",
        maxWidth: "320px",
        height: "4px",
        display: "flex",
        borderRadius: "2px",
        overflow: "hidden",
        opacity: 0.7,
      }}
    >
      {seg(counts.tailwind, STANCE_COLOR.tailwind, "Tailwind")}
      {seg(counts.mixed,    STANCE_COLOR.mixed,    "Mixed")}
      {seg(counts.neutral,  STANCE_COLOR.neutral,  "Neutral")}
      {seg(counts.headwind, STANCE_COLOR.headwind, "Headwind")}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Table of contents — quiet list with stance dots, clickable to jump.
// ---------------------------------------------------------------------------
function TableOfContents({ sections, onJump }) {
  return (
    <div style={{ padding: "0 28px 28px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "14px" }}>
        <span style={{ flex: 1, height: "1px", background: "var(--border-subtle)" }} />
        <span
          style={{
            fontFamily: MONO,
            fontSize: "9.5px",
            fontWeight: 700,
            letterSpacing: "0.22em",
            color: "var(--color-text-muted)",
            textTransform: "uppercase",
          }}
        >
          Contents
        </span>
        <span style={{ flex: 1, height: "1px", background: "var(--border-subtle)" }} />
      </div>

      <ol style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "2px" }}>
        {sections.map((sec, idx) => {
          const color = STANCE_COLOR[sec.stance] || STANCE_COLOR.neutral;
          return (
            <li key={idx}>
              <button
                type="button"
                onClick={() => onJump(idx)}
                style={{
                  display: "grid",
                  gridTemplateColumns: "28px 1fr auto",
                  alignItems: "center",
                  gap: "12px",
                  width: "100%",
                  padding: "10px 8px",
                  border: "none",
                  background: "transparent",
                  cursor: "pointer",
                  borderRadius: "6px",
                  textAlign: "left",
                  transition: "background 0.15s",
                  borderBottom: idx === sections.length - 1 ? "none" : "1px dashed var(--border-subtle)",
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "var(--color-bg-card-hover, rgba(255,255,255,0.03))")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
              >
                <span
                  style={{
                    fontFamily: MONO,
                    fontSize: "11px",
                    fontWeight: 700,
                    color: "var(--color-text-muted)",
                    letterSpacing: "0.05em",
                  }}
                >
                  {String(idx + 1).padStart(2, "0")}
                </span>
                <span
                  style={{
                    fontSize: "13.5px",
                    fontWeight: 600,
                    color: "var(--color-text-primary)",
                    letterSpacing: "-0.005em",
                  }}
                >
                  {sec.title}
                </span>
                <span
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "6px",
                    fontFamily: MONO,
                    fontSize: "9.5px",
                    fontWeight: 700,
                    letterSpacing: "0.14em",
                    color,
                    textTransform: "uppercase",
                  }}
                >
                  <span style={{ width: "5px", height: "5px", borderRadius: "50%", background: color }} />
                  {STANCE_LABEL[sec.stance] || "—"}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section card — numbered, stance ribbon, serif body, ticker chips.
// ---------------------------------------------------------------------------
function SectionCard({ index, section, onTickerClick }) {
  const color = STANCE_COLOR[section.stance] || STANCE_COLOR.neutral;
  return (
    <article
      style={{
        background: "var(--color-bg-card)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-card)",
        overflow: "hidden",
      }}
    >
      {/* Stance ribbon — 3px accent at the top */}
      <div style={{ height: "3px", background: color, opacity: 0.85 }} />

      <div style={{ padding: "20px 22px 22px" }}>
        {/* Header row — number · title · stance tag */}
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            gap: "12px",
            marginBottom: "14px",
            flexWrap: "wrap",
          }}
        >
          <div style={{ display: "flex", alignItems: "baseline", gap: "12px" }}>
            <span
              style={{
                fontFamily: MONO,
                fontSize: "11px",
                fontWeight: 700,
                letterSpacing: "0.16em",
                color: "var(--color-text-muted)",
              }}
            >
              {String(index + 1).padStart(2, "0")}
            </span>
            <h3
              style={{
                fontSize: "14px",
                fontWeight: 700,
                color: "var(--color-text-primary)",
                margin: 0,
                letterSpacing: "-0.005em",
              }}
            >
              {section.title}
            </h3>
          </div>
          <span
            style={{
              fontFamily: MONO,
              fontSize: "9.5px",
              fontWeight: 700,
              letterSpacing: "0.16em",
              textTransform: "uppercase",
              color,
              border: `1px solid color-mix(in srgb, ${color} 32%, transparent)`,
              background: `color-mix(in srgb, ${color} 10%, transparent)`,
              padding: "2px 8px",
              borderRadius: "4px",
            }}
          >
            {STANCE_LABEL[section.stance] || "—"}
          </span>
        </div>

        {/* Body — serif, comfortable line-height, larger than default */}
        <p
          style={{
            fontSize: "14.5px",
            lineHeight: 1.7,
            color: "var(--color-text-secondary)",
            whiteSpace: "pre-wrap",
            margin: 0,
            fontFamily: SERIF,
            letterSpacing: "-0.003em",
          }}
        >
          {section.body}
        </p>

        {/* Key tickers — mono chips with click-to-company */}
        {section.key_tickers && section.key_tickers.length > 0 && (
          <div
            style={{
              marginTop: "14px",
              paddingTop: "14px",
              borderTop: "1px dashed var(--border-subtle)",
              display: "flex",
              flexWrap: "wrap",
              gap: "6px",
              alignItems: "center",
            }}
          >
            <span
              style={{
                fontFamily: MONO,
                fontSize: "9.5px",
                fontWeight: 700,
                letterSpacing: "0.18em",
                textTransform: "uppercase",
                color: "var(--color-text-muted)",
                marginRight: "4px",
              }}
            >
              Mentioned
            </span>
            {section.key_tickers.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => onTickerClick?.(t)}
                style={{
                  padding: "3px 8px",
                  borderRadius: "4px",
                  background: "transparent",
                  color: "var(--color-text-secondary)",
                  border: "1px solid var(--border-subtle)",
                  fontSize: "10.5px",
                  fontFamily: MONO,
                  fontWeight: 700,
                  letterSpacing: "0.04em",
                  cursor: "pointer",
                  transition: "border-color 0.15s, color 0.15s",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = "var(--color-accent-primary)";
                  e.currentTarget.style.color = "var(--color-accent-primary)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = "var(--border-subtle)";
                  e.currentTarget.style.color = "var(--color-text-secondary)";
                }}
              >
                {t}
              </button>
            ))}
          </div>
        )}
      </div>
    </article>
  );
}

// ---------------------------------------------------------------------------
// Floating dot-rail — right edge, jumps between sections.
// Hidden on narrow viewports where it'd crowd the content.
// ---------------------------------------------------------------------------
function SectionDotRail({ sections, activeIdx, onJump }) {
  return (
    <div
      aria-hidden
      className="mb-dot-rail"
      style={{
        position: "absolute",
        right: "14px",
        top: "50%",
        transform: "translateY(-50%)",
        display: "flex",
        flexDirection: "column",
        gap: "8px",
        padding: "8px 6px",
        background: "rgba(0,0,0,0.18)",
        backdropFilter: "blur(6px)",
        WebkitBackdropFilter: "blur(6px)",
        borderRadius: "999px",
        border: "1px solid var(--border-subtle)",
        zIndex: 5,
      }}
    >
      {sections.map((sec, idx) => {
        const color = STANCE_COLOR[sec.stance] || STANCE_COLOR.neutral;
        const active = idx === activeIdx;
        return (
          <button
            key={idx}
            type="button"
            onClick={() => onJump(idx)}
            aria-label={`Jump to ${sec.title}`}
            title={sec.title}
            style={{
              width: active ? "10px" : "6px",
              height: active ? "10px" : "6px",
              padding: 0,
              borderRadius: "50%",
              background: active ? color : "color-mix(in srgb, var(--color-text-muted) 50%, transparent)",
              border: "none",
              cursor: "pointer",
              transition: "width 0.18s, height 0.18s, background 0.18s",
            }}
          />
        );
      })}
      <style>{`
        @media (max-width: 720px) {
          .mb-dot-rail { display: none; }
        }
      `}</style>
    </div>
  );
}
