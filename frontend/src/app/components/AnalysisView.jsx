"use client";

/**
 * AnalysisView — Deep-Dive on a single stock, Editorial Quiet edition.
 *
 * The old design leaned on gradients, emoji icons, glass cards and score
 * rings — all the "AI-app" tropes we're rooting out. This rewrite mirrors the
 * rest of the product: hairlines, mono labels, serif italic for human prose,
 * single indigo accent. Numbers do the talking.
 *
 * Functional upgrade — the analysis itself is richer:
 *   • One-liner (what this company is + why it matters, max ~22 words)
 *   • Moat assessment (one line)
 *   • Valuation Read (EXPENSIVE / FAIR / CHEAP with the basis cited)
 *   • Bull Case × 3 + Bear Case × 3 (the centerpiece — falsifiable, cited)
 *   • Financial Health (4 horizontal percentile bars vs sector peers)
 *   • Key Risks (stock-specific, not industry boilerplate)
 *   • What to Watch (3 concrete observable triggers)
 *   • Stance + thesis + optional target range (compliance: assessment language)
 *   • Same-sector alternatives (deterministic, ROE-ranked from grounding)
 *   • Price chart (existing component)
 *
 * Loader is delegated to MissionControlLoader(variant="analysis") for parity
 * with the rest of the app's loading vocabulary.
 */

import { useState, useEffect } from "react";
import StockChart from "./StockChart";
import MissionControlLoader from "./MissionControlLoader";

import { API_BASE as _SHARED_API_BASE } from "../lib/api";
import { claimText, claimSource } from "../lib/claim";
import { readSSE } from "../lib/sseStream";
const API_BASE = _SHARED_API_BASE;

// Compliance — assessment language only. Legacy buy/sell/hold aliased so any
// cached older responses still render with the correct soft labels.
const STANCE_COLORS = {
  BULLISH: "var(--color-accent-green)",
  NEUTRAL: "var(--color-accent-amber)",
  CAUTIOUS: "var(--color-accent-red)",
  BUY: "var(--color-accent-green)",
  HOLD: "var(--color-accent-amber)",
  SELL: "var(--color-accent-red)",
};
const STANCE_LABELS = {
  BULLISH: "BULLISH", NEUTRAL: "NEUTRAL", CAUTIOUS: "CAUTIOUS",
  BUY: "BULLISH", HOLD: "NEUTRAL", SELL: "CAUTIOUS",
};
const MOAT_COLORS = {
  WIDE: "var(--color-accent-green)",
  NARROW: "var(--color-accent-amber)",
  NONE: "var(--color-accent-red)",
};
const VALUATION_COLORS = {
  CHEAP: "var(--color-accent-green)",
  FAIR: "var(--color-text-secondary)",
  EXPENSIVE: "var(--color-accent-red)",
};
const IMPACT_COLORS = {
  POSITIVE: "var(--color-accent-green)",
  NEGATIVE: "var(--color-accent-red)",
  NEUTRAL: "var(--color-text-muted)",
};

const SERIF = "'Georgia', 'Iowan Old Style', 'Apple Garamond', 'Times New Roman', serif";
const MONO = "var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace)";

// ---------------------------------------------------------------------------
// Small reusable atoms — kept inside the file so the component is self-contained
// ---------------------------------------------------------------------------

// BackButton — sits above the page header. Mono caps, hairline border, minimal.
// Accessibility: real <button> with type="button" and aria-label so screen
// readers announce the destination ("Back to Portfolio") not just "Back".
function BackButton({ onBack, label }) {
  return (
    <button
      type="button"
      onClick={onBack}
      aria-label={`Back to ${label}`}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "8px",
        padding: "7px 12px 7px 9px",
        marginBottom: "16px",
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-control)",
        background: "transparent",
        color: "var(--color-text-muted)",
        fontSize: "11px",
        fontWeight: 700,
        fontFamily: MONO,
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        cursor: "pointer",
        transition: "border-color 0.15s, color 0.15s",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = "var(--border-strong)";
        e.currentTarget.style.color = "var(--color-text-primary)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = "var(--border-subtle)";
        e.currentTarget.style.color = "var(--color-text-muted)";
      }}
    >
      <span aria-hidden style={{ fontSize: "13px", lineHeight: 1 }}>←</span>
      <span>Back to {label}</span>
    </button>
  );
}

function SectionLabel({ children }) {
  return (
    <h4
      style={{
        fontSize: "10.5px",
        fontWeight: 700,
        textTransform: "uppercase",
        letterSpacing: "0.18em",
        color: "var(--color-text-muted)",
        marginBottom: "14px",
        fontFamily: MONO,
      }}
    >
      {children}
    </h4>
  );
}

function Card({ children, style }) {
  return (
    <div
      style={{
        padding: "22px 24px",
        background: "var(--color-bg-card)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-card)",
        ...style,
      }}
    >
      {children}
    </div>
  );
}

function Hairline({ width = "100%" }) {
  return (
    <div
      aria-hidden
      style={{
        width,
        height: "1px",
        background: "var(--border-subtle)",
        margin: "16px 0",
      }}
    />
  );
}

// Horizontal percentile bar — replaces ScoreRing. Reads as "where this stock
// sits in its sector" in a single glance. Tick at the 50th-percentile mark
// gives the median anchor.
function PercentileBar({ label, value, percentile, invert = false }) {
  // invert = lower-is-better (debt). We display percentile as-is but color flips
  // so high-percentile-debt reads red.
  const pct = percentile == null ? null : Math.max(0, Math.min(100, percentile));
  const goodSide = invert ? pct != null && pct <= 35 : pct != null && pct >= 65;
  const badSide  = invert ? pct != null && pct >= 65 : pct != null && pct <= 35;
  const color = goodSide
    ? "var(--color-accent-green)"
    : badSide
    ? "var(--color-accent-red)"
    : "var(--color-text-secondary)";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          fontFamily: MONO,
          fontSize: "11px",
        }}
      >
        <span
          style={{
            color: "var(--color-text-muted)",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            fontWeight: 600,
          }}
        >
          {label}
        </span>
        <span
          style={{
            color: "var(--color-text-primary)",
            fontWeight: 700,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {value || "—"}
        </span>
      </div>
      <div
        style={{
          position: "relative",
          height: "4px",
          background: "rgba(255,255,255,0.06)",
          borderRadius: "2px",
          overflow: "visible",
        }}
      >
        {pct != null && (
          <div
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              height: "100%",
              width: `${pct}%`,
              background: color,
              borderRadius: "2px",
              transition: "width 0.8s cubic-bezier(0.4, 0, 0.2, 1)",
            }}
          />
        )}
        {/* median tick */}
        <div
          aria-hidden
          style={{
            position: "absolute",
            left: "50%",
            top: "-2px",
            bottom: "-2px",
            width: "1px",
            background: "rgba(255,255,255,0.18)",
          }}
        />
      </div>
      <div
        style={{
          fontSize: "10px",
          color: "var(--color-text-muted)",
          fontFamily: MONO,
          letterSpacing: "0.05em",
        }}
      >
        {pct != null ? `${pct}th percentile vs sector` : "no peer data"}
      </div>
    </div>
  );
}

// Bull/Bear column — a vertical list of cited points. Headline is the only
// place we accent color (green for bull, red for bear).
function CaseColumn({ side, items }) {
  const isBull = side === "bull";
  const accent = isBull ? "var(--color-accent-green)" : "var(--color-accent-red)";
  const title = isBull ? "Bull case" : "Bear case";
  const glyph = isBull ? "+" : "−";

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "10px",
          marginBottom: "14px",
        }}
      >
        <span
          style={{
            fontFamily: MONO,
            fontSize: "10.5px",
            fontWeight: 700,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: accent,
          }}
        >
          {title}
        </span>
        <span
          style={{
            flex: 1,
            height: "1px",
            background: "var(--border-subtle)",
          }}
        />
      </div>
      <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "14px" }}>
        {items && items.length > 0 ? (
          items.map((it, i) => (
            <li
              key={i}
              style={{
                display: "grid",
                gridTemplateColumns: "16px 1fr",
                gap: "10px",
                alignItems: "flex-start",
              }}
              title={claimSource(it) || ""}
            >
              <span
                style={{
                  fontFamily: MONO,
                  fontSize: "14px",
                  fontWeight: 700,
                  color: accent,
                  lineHeight: 1.5,
                }}
              >
                {glyph}
              </span>
              <span
                style={{
                  fontFamily: SERIF,
                  fontSize: "14.5px",
                  lineHeight: 1.55,
                  color: "var(--color-text-primary)",
                  letterSpacing: "-0.003em",
                }}
              >
                {claimText(it)}
              </span>
            </li>
          ))
        ) : (
          <li style={{ fontSize: "13px", color: "var(--color-text-muted)", fontStyle: "italic" }}>
            Not enough grounded data to construct this side.
          </li>
        )}
      </ul>
    </div>
  );
}

function formatINR(n) {
  if (n == null || isNaN(n)) return "—";
  return `₹${Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

// Confidence tooltip — shows the user EXACTLY which grounding signals shaped
// the score so it doesn't feel like a black-box vibes number. Hover-only text,
// no chrome — uses the native title attribute.
function buildConfidenceTooltip(verdict) {
  const b = verdict?.confidence_basis;
  if (!b) return "Confidence reflects data completeness behind this brief.";
  const lines = [
    `Score: ${verdict.confidence}% (${verdict.confidence_label || "—"})`,
    "",
    "Computed from real data signals:",
    `• Missing core financials: ${b.missing_core_financials}/5`,
    `• Sector peers sampled: ${b.peers_sampled}`,
    `• News items grounding catalysts: ${b.news_count}`,
    `• Data gaps admitted by the model: ${b.data_gaps}`,
    `• Claims removed by fact-check verifier: ${b.claims_removed}`,
  ];
  return lines.join("\n");
}
function formatCompact(n) {
  if (n == null || isNaN(n)) return "—";
  const abs = Math.abs(n);
  if (abs >= 1e12) return `₹${(n / 1e12).toFixed(2)}T`;
  if (abs >= 1e10) return `₹${(n / 1e7).toFixed(0)} Cr`;   // ≥1000 Cr
  if (abs >= 1e7)  return `₹${(n / 1e7).toFixed(1)} Cr`;
  if (abs >= 1e5)  return `₹${(n / 1e5).toFixed(1)} L`;
  return `₹${n}`;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function AnalysisView({ initialTicker, onBack, backLabel = "Back" }) {
  const [ticker, setTicker] = useState(initialTicker || "");
  const [searchQuery, setSearchQuery] = useState(initialTicker || "");
  const [searchResults, setSearchResults] = useState([]);
  const [stockMeta, setStockMeta] = useState(null);
  const [showDropdown, setShowDropdown] = useState(false);

  const [deepDive, setDeepDive] = useState(null);
  const [ddLoading, setDdLoading] = useState(false);
  const [ddSteps, setDdSteps] = useState([]);
  const [ddError, setDdError] = useState(null);

  // Sync internal state when the parent passes a NEW initialTicker. Without
  // this, useState(initialTicker) only captures the prop on first mount, so
  // clicking another stock in PortfolioView reuses the original ticker and
  // never re-runs the deep dive. Reset the previously-fetched stockMeta too
  // so the hero strip doesn't show the old company's name/price while the
  // new analysis loads.
  useEffect(() => {
    if (initialTicker && initialTicker !== ticker) {
      setTicker(initialTicker);
      setSearchQuery(initialTicker);
      setStockMeta(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialTicker]);

  // Auto-trigger when ticker changes (from prop sync above, search dropdown,
  // or "alternatives" click further down the view).
  useEffect(() => {
    if (ticker) runDeepDive(ticker);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker]);

  const handleSearch = async (q) => {
    setSearchQuery(q);
    if (q.length < 2) { setSearchResults([]); setShowDropdown(false); return; }
    try {
      const res = await fetch(`${API_BASE}/api/stocks/search?q=${q}&limit=8`);
      const data = await res.json();
      setSearchResults(data);
      setShowDropdown(true);
    } catch { setSearchResults([]); }
  };

  const selectStock = (stock) => {
    setTicker(stock.ticker);
    setSearchQuery(stock.ticker);
    setStockMeta(stock);
    setShowDropdown(false);
    setSearchResults([]);
  };

  const runDeepDive = async (t) => {
    setDdLoading(true);
    setDeepDive(null);
    setDdSteps([]);
    setDdError(null);

    try {
      const response = await fetch(`${API_BASE}/api/analysis/deep-dive`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker: t }),
      });

      for await (const data of readSSE(response)) {
        if (data === "[DONE]") { setDdLoading(false); break; }
        if (data.type === "step") setDdSteps((prev) => [...prev, data.message]);
        else if (data.type === "error") { setDdError(data.message); setDdLoading(false); }
        else if (data.type === "result") { setDeepDive(data); setDdLoading(false); }
      }
    } catch (err) {
      setDdError(String(err));
      setDdLoading(false);
    }
  };

  // 52w position read — used in the hero strip.
  const snap = deepDive?.snapshot || {};
  const price = snap.current_price ?? stockMeta?.current_price;
  const changePct = snap.change_percent ?? stockMeta?.change_percent;
  let band52w = null;
  if (price && snap["52w_high"] && snap["52w_low"] && snap["52w_high"] > snap["52w_low"]) {
    band52w = Math.round(((price - snap["52w_low"]) / (snap["52w_high"] - snap["52w_low"])) * 100);
  }

  const fin = deepDive?.financials || {};
  const pct = fin.vs_peers || {};

  return (
    <div>
      {/* Back button — only renders when we have somewhere to go back to. */}
      {onBack && <BackButton onBack={onBack} label={backLabel} />}

      {/* Page header */}
      <div style={{ marginBottom: "24px" }}>
        <h2
          style={{
            fontSize: "22px",
            fontWeight: 700,
            color: "var(--color-text-primary)",
            letterSpacing: "-0.01em",
          }}
        >
          Deep dive
        </h2>
        <p
          style={{
            fontSize: "12.5px",
            color: "var(--color-text-muted)",
            marginTop: "4px",
            fontFamily: MONO,
            letterSpacing: "0.04em",
          }}
        >
          Grounded equity brief — every number cited from a real source.
        </p>
      </div>

      {/* Search */}
      <div style={{ marginBottom: "24px", position: "relative", maxWidth: "520px" }}>
        <div style={{ position: "relative" }}>
          <input
            type="text"
            placeholder="Search a stock (e.g. RELIANCE, TCS, INFY)…"
            value={searchQuery}
            onChange={(e) => handleSearch(e.target.value)}
            onFocus={() => { if (searchResults.length) setShowDropdown(true); }}
            style={{
              width: "100%",
              padding: "12px 18px 12px 40px",
              borderRadius: "var(--radius-control)",
              fontSize: "13.5px",
              border: "1px solid var(--border-subtle)",
              outline: "none",
              background: "var(--color-bg-card)",
              color: "var(--color-text-primary)",
              fontFamily: MONO,
              letterSpacing: "0.01em",
            }}
          />
          <svg
            style={{
              position: "absolute",
              left: "14px",
              top: "50%",
              transform: "translateY(-50%)",
              width: "16px",
              height: "16px",
              color: "var(--color-text-muted)",
            }}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>

        {showDropdown && searchResults.length > 0 && (
          <div
            style={{
              position: "absolute",
              top: "100%",
              left: 0,
              right: 0,
              marginTop: "6px",
              zIndex: 20,
              background: "var(--color-bg-card)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--radius-card)",
              overflow: "hidden",
              boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
            }}
          >
            {searchResults.map((s) => (
              <div
                key={s.ticker}
                onClick={() => selectStock(s)}
                style={{
                  padding: "11px 14px",
                  cursor: "pointer",
                  borderBottom: "1px solid var(--border-subtle)",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "var(--color-bg-card-hover, rgba(255,255,255,0.03))")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
              >
                <div>
                  <span style={{ fontWeight: 700, fontSize: "13px", color: "var(--color-text-primary)", fontFamily: MONO }}>{s.ticker}</span>
                  <span style={{ color: "var(--color-text-muted)", marginLeft: "10px", fontSize: "13px" }}>{s.name}</span>
                </div>
                <span
                  style={{
                    padding: "2px 8px",
                    fontSize: "10px",
                    fontWeight: 600,
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                    color: "var(--color-text-muted)",
                    border: "1px solid var(--border-subtle)",
                    borderRadius: "4px",
                    fontFamily: MONO,
                  }}
                >
                  {s.sector}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Empty state — editorial, no emoji */}
      {!ticker && (
        <Card style={{ padding: "64px 28px" }}>
          <div style={{ maxWidth: "440px", margin: "0 auto", textAlign: "center" }}>
            <div
              style={{
                fontFamily: MONO,
                fontSize: "10.5px",
                fontWeight: 700,
                letterSpacing: "0.22em",
                textTransform: "uppercase",
                color: "var(--color-text-muted)",
                marginBottom: "20px",
              }}
            >
              Equity brief · awaiting ticker
            </div>
            <p
              style={{
                fontFamily: SERIF,
                fontStyle: "italic",
                fontSize: "20px",
                lineHeight: 1.5,
                color: "var(--color-text-primary)",
                marginBottom: "20px",
                letterSpacing: "-0.005em",
              }}
            >
              Search any NSE-listed company above.
            </p>
            <p style={{ fontSize: "13px", color: "var(--color-text-muted)", lineHeight: 1.6 }}>
              You&rsquo;ll get a grounded brief — bull case, bear case, valuation read,
              peer-relative financial health, key risks, and concrete triggers to watch.
              Every number cites a source.
            </p>
          </div>
        </Card>
      )}

      {ticker && (
        <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          {/* Hero strip — mono ticker, sector chip, price + 52w position. No
              gradient avatar block; the data IS the headline. */}
          {(stockMeta || deepDive) && (
            <Card
              style={{
                padding: "18px 22px",
                display: "flex",
                alignItems: "center",
                gap: "20px",
                flexWrap: "wrap",
                borderLeft: deepDive?.verdict?.action
                  ? `3px solid ${STANCE_COLORS[deepDive.verdict.action] || "var(--border-strong)"}`
                  : "3px solid var(--border-strong)",
              }}
            >
              <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.15 }}>
                <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                  <span
                    style={{
                      fontSize: "20px",
                      fontWeight: 800,
                      color: "var(--color-text-primary)",
                      fontFamily: MONO,
                      letterSpacing: "0.01em",
                    }}
                  >
                    {ticker}
                  </span>
                  <span
                    style={{
                      padding: "2px 8px",
                      fontSize: "9.5px",
                      fontWeight: 700,
                      letterSpacing: "0.14em",
                      textTransform: "uppercase",
                      color: "var(--color-text-muted)",
                      border: "1px solid var(--border-subtle)",
                      borderRadius: "4px",
                      fontFamily: MONO,
                    }}
                  >
                    {stockMeta?.sector || deepDive?.sector || "—"}
                  </span>
                </div>
                <span style={{ fontSize: "13px", color: "var(--color-text-muted)", marginTop: "3px" }}>
                  {stockMeta?.name || deepDive?.company || ""}
                </span>
              </div>

              {price != null && price > 0 && (
                <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", lineHeight: 1.15 }}>
                  <span style={{ fontFamily: MONO, fontSize: "9.5px", letterSpacing: "0.16em", textTransform: "uppercase", color: "var(--color-text-muted)", fontWeight: 700 }}>LTP</span>
                  <div style={{ display: "flex", alignItems: "baseline", gap: "8px", marginTop: "2px" }}>
                    <span
                      style={{
                        fontSize: "20px",
                        fontWeight: 700,
                        color: "var(--color-text-primary)",
                        fontFamily: MONO,
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      {formatINR(price)}
                    </span>
                    {changePct != null && (
                      <span
                        style={{
                          fontSize: "12.5px",
                          fontWeight: 700,
                          fontFamily: MONO,
                          color: changePct >= 0 ? "var(--color-accent-green)" : "var(--color-accent-red)",
                          fontVariantNumeric: "tabular-nums",
                        }}
                      >
                        {changePct >= 0 ? "▲ +" : "▼ "}{Math.abs(changePct).toFixed(2)}%
                      </span>
                    )}
                  </div>
                </div>
              )}

              {band52w != null && (
                <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", lineHeight: 1.15, minWidth: "160px" }}>
                  <span style={{ fontFamily: MONO, fontSize: "9.5px", letterSpacing: "0.16em", textTransform: "uppercase", color: "var(--color-text-muted)", fontWeight: 700 }}>52W Position</span>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px", marginTop: "6px" }}>
                    <div style={{ position: "relative", width: "120px", height: "4px", background: "rgba(255,255,255,0.06)", borderRadius: "2px" }}>
                      <div style={{ position: "absolute", left: `calc(${band52w}% - 4px)`, top: "-2px", width: "8px", height: "8px", background: "var(--color-accent-primary)", borderRadius: "50%" }} />
                    </div>
                    <span style={{ fontSize: "12px", fontFamily: MONO, fontWeight: 700, color: "var(--color-text-primary)", fontVariantNumeric: "tabular-nums" }}>{band52w}%</span>
                  </div>
                </div>
              )}

              {snap.market_cap && (
                <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", lineHeight: 1.15 }}>
                  <span style={{ fontFamily: MONO, fontSize: "9.5px", letterSpacing: "0.16em", textTransform: "uppercase", color: "var(--color-text-muted)", fontWeight: 700 }}>Mcap</span>
                  <span style={{ fontFamily: MONO, fontSize: "13px", fontWeight: 700, color: "var(--color-text-primary)", marginTop: "4px", fontVariantNumeric: "tabular-nums" }}>
                    {formatCompact(snap.market_cap)}
                  </span>
                </div>
              )}

              <div style={{ marginLeft: "auto" }}>
                <button
                  onClick={() => runDeepDive(ticker)}
                  disabled={ddLoading}
                  style={{
                    padding: "7px 13px",
                    borderRadius: "var(--radius-control)",
                    fontSize: "11px",
                    fontWeight: 600,
                    letterSpacing: "0.04em",
                    border: "1px solid var(--border-subtle)",
                    background: "transparent",
                    color: ddLoading ? "var(--color-text-muted)" : "var(--color-text-secondary)",
                    cursor: ddLoading ? "default" : "pointer",
                    fontFamily: MONO,
                  }}
                >
                  {ddLoading ? "Working…" : "↻ Re-run"}
                </button>
              </div>
            </Card>
          )}

          {/* Loader */}
          {ddLoading && (
            <MissionControlLoader
              steps={ddSteps}
              variant="analysis"
              compact={true}
            />
          )}

          {/* Error */}
          {ddError && !ddLoading && (
            <Card style={{ borderColor: "var(--color-accent-red)", background: "rgba(239,68,68,0.04)" }}>
              <div
                style={{
                  fontFamily: MONO,
                  fontSize: "10.5px",
                  fontWeight: 700,
                  letterSpacing: "0.16em",
                  textTransform: "uppercase",
                  color: "var(--color-accent-red)",
                  marginBottom: "8px",
                }}
              >
                Analysis failed
              </div>
              <div style={{ fontSize: "13.5px", color: "var(--color-text-secondary)", lineHeight: 1.5 }}>{ddError}</div>
              <button
                onClick={() => runDeepDive(ticker)}
                style={{
                  marginTop: "14px",
                  padding: "6px 14px",
                  borderRadius: "var(--radius-control)",
                  fontSize: "11px",
                  fontWeight: 600,
                  border: "1px solid var(--color-accent-red)",
                  background: "transparent",
                  color: "var(--color-accent-red)",
                  cursor: "pointer",
                  fontFamily: MONO,
                  letterSpacing: "0.04em",
                }}
              >
                Retry
              </button>
            </Card>
          )}

          {deepDive && (
            <>
              {/* One-liner — the headline read of the company. Serif italic, the
                  same voice the loaders use, so the analysis FEELS continuous
                  with the loading screen. */}
              {deepDive.one_liner && (
                <Card style={{ padding: "26px 28px" }}>
                  <div
                    style={{
                      fontFamily: MONO,
                      fontSize: "10.5px",
                      fontWeight: 700,
                      letterSpacing: "0.18em",
                      textTransform: "uppercase",
                      color: "var(--color-text-muted)",
                      marginBottom: "12px",
                    }}
                  >
                    The read
                  </div>
                  <p
                    style={{
                      fontFamily: SERIF,
                      fontSize: "20px",
                      lineHeight: 1.5,
                      color: "var(--color-text-primary)",
                      letterSpacing: "-0.005em",
                      margin: 0,
                    }}
                  >
                    {deepDive.one_liner}
                  </p>
                </Card>
              )}

              {/* Stance + thesis + (optional) target range — compact, no big
                  colored pill. The borderLeft on the hero already encodes the
                  stance color; here we just read it back in text. */}
              {deepDive.verdict && (
                <Card>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "auto 1fr auto",
                      gap: "24px",
                      alignItems: "center",
                      marginBottom: "14px",
                    }}
                  >
                    <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.15 }}>
                      <span
                        style={{
                          fontFamily: MONO,
                          fontSize: "9.5px",
                          fontWeight: 700,
                          letterSpacing: "0.16em",
                          textTransform: "uppercase",
                          color: "var(--color-text-muted)",
                          marginBottom: "4px",
                        }}
                      >
                        Stance
                      </span>
                      <span
                        style={{
                          fontFamily: MONO,
                          fontSize: "18px",
                          fontWeight: 800,
                          letterSpacing: "0.04em",
                          color: STANCE_COLORS[deepDive.verdict.action] || "var(--color-text-primary)",
                        }}
                      >
                        {STANCE_LABELS[deepDive.verdict.action] || deepDive.verdict.action}
                      </span>
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.15 }}>
                      <span
                        style={{
                          fontFamily: MONO,
                          fontSize: "9.5px",
                          fontWeight: 700,
                          letterSpacing: "0.16em",
                          textTransform: "uppercase",
                          color: "var(--color-text-muted)",
                          marginBottom: "4px",
                        }}
                      >
                        Data confidence
                      </span>
                      <div style={{ display: "flex", alignItems: "center", gap: "10px" }} title={buildConfidenceTooltip(deepDive.verdict)}>
                        <div style={{ position: "relative", width: "120px", height: "3px", background: "rgba(255,255,255,0.06)", borderRadius: "2px" }}>
                          <div
                            style={{
                              position: "absolute",
                              left: 0,
                              top: 0,
                              height: "100%",
                              width: `${deepDive.verdict.confidence || 0}%`,
                              background:
                                (deepDive.verdict.confidence || 0) >= 70 ? "var(--color-accent-green)"
                                : (deepDive.verdict.confidence || 0) >= 40 ? "var(--color-accent-amber)"
                                : "var(--color-accent-red)",
                              borderRadius: "2px",
                              transition: "width 0.8s cubic-bezier(0.4, 0, 0.2, 1)",
                            }}
                          />
                        </div>
                        <span
                          style={{
                            fontFamily: MONO,
                            fontSize: "13px",
                            fontWeight: 700,
                            color: "var(--color-text-primary)",
                            fontVariantNumeric: "tabular-nums",
                          }}
                        >
                          {deepDive.verdict.confidence || 0}%
                        </span>
                        {deepDive.verdict.confidence_label && (
                          <span
                            style={{
                              fontFamily: MONO,
                              fontSize: "9.5px",
                              fontWeight: 700,
                              letterSpacing: "0.1em",
                              textTransform: "uppercase",
                              color: "var(--color-text-muted)",
                            }}
                          >
                            · {deepDive.verdict.confidence_label}
                          </span>
                        )}
                      </div>
                    </div>

                    {(deepDive.verdict.target_low || deepDive.verdict.target_high) && (
                      <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.15, alignItems: "flex-end" }}>
                        <span
                          style={{
                            fontFamily: MONO,
                            fontSize: "9.5px",
                            fontWeight: 700,
                            letterSpacing: "0.16em",
                            textTransform: "uppercase",
                            color: "var(--color-text-muted)",
                            marginBottom: "4px",
                          }}
                        >
                          Target range
                        </span>
                        <span
                          style={{
                            fontFamily: MONO,
                            fontSize: "13px",
                            fontWeight: 700,
                            color: "var(--color-text-primary)",
                            fontVariantNumeric: "tabular-nums",
                          }}
                        >
                          {formatINR(deepDive.verdict.target_low)} — {formatINR(deepDive.verdict.target_high)}
                        </span>
                      </div>
                    )}
                  </div>

                  {claimText(deepDive.verdict.thesis) && (
                    <p
                      title={claimSource(deepDive.verdict.thesis) || ""}
                      style={{
                        fontFamily: SERIF,
                        fontStyle: "italic",
                        fontSize: "15px",
                        lineHeight: 1.6,
                        color: "var(--color-text-secondary)",
                        margin: 0,
                        paddingTop: "14px",
                        borderTop: "1px solid var(--border-subtle)",
                        letterSpacing: "-0.003em",
                      }}
                    >
                      &ldquo;{claimText(deepDive.verdict.thesis)}&rdquo;
                    </p>
                  )}
                </Card>
              )}

              {/* Bull / Bear — the centerpiece. Side-by-side on desktop, stacked
                  on mobile via responsive-grid-2 class already used elsewhere. */}
              <Card style={{ padding: "26px 28px" }}>
                <div className="responsive-grid-2" style={{ gap: "32px" }}>
                  <CaseColumn side="bull" items={deepDive.bull_case} />
                  <CaseColumn side="bear" items={deepDive.bear_case} />
                </div>
              </Card>

              {/* Moat + Valuation — paired editorial cards. */}
              <div className="responsive-grid-2" style={{ gap: "20px" }}>
                <Card>
                  <SectionLabel>Competitive moat</SectionLabel>
                  <div style={{ display: "flex", alignItems: "baseline", gap: "10px", marginBottom: "10px" }}>
                    <span
                      style={{
                        fontFamily: MONO,
                        fontSize: "20px",
                        fontWeight: 800,
                        letterSpacing: "0.04em",
                        color: MOAT_COLORS[deepDive.moat_rating] || "var(--color-text-primary)",
                      }}
                    >
                      {deepDive.moat_rating || "NARROW"}
                    </span>
                    <span style={{ fontSize: "12px", color: "var(--color-text-muted)", fontFamily: MONO, letterSpacing: "0.04em" }}>
                      structural advantage
                    </span>
                  </div>
                  <p
                    title={claimSource(deepDive.moat_reason) || ""}
                    style={{ fontSize: "14px", color: "var(--color-text-secondary)", lineHeight: 1.6, margin: 0 }}
                  >
                    {claimText(deepDive.moat_reason) || "Moat assessment unavailable."}
                  </p>
                </Card>

                <Card>
                  <SectionLabel>Valuation read</SectionLabel>
                  {deepDive.valuation_read ? (
                    <>
                      <div style={{ display: "flex", alignItems: "baseline", gap: "10px", marginBottom: "10px" }}>
                        <span
                          style={{
                            fontFamily: MONO,
                            fontSize: "20px",
                            fontWeight: 800,
                            letterSpacing: "0.04em",
                            color: VALUATION_COLORS[deepDive.valuation_read.stance] || "var(--color-text-primary)",
                          }}
                        >
                          {deepDive.valuation_read.stance || "FAIR"}
                        </span>
                        {snap.pe_ratio != null && (
                          <span style={{ fontSize: "12px", color: "var(--color-text-muted)", fontFamily: MONO, letterSpacing: "0.04em", fontVariantNumeric: "tabular-nums" }}>
                            P/E {Number(snap.pe_ratio).toFixed(1)}
                          </span>
                        )}
                      </div>
                      <p
                        title={claimSource(deepDive.valuation_read.basis) || ""}
                        style={{ fontSize: "14px", color: "var(--color-text-secondary)", lineHeight: 1.6, margin: 0 }}
                      >
                        {claimText(deepDive.valuation_read.basis) || "Valuation basis unavailable."}
                      </p>
                    </>
                  ) : (
                    <p style={{ fontSize: "13px", color: "var(--color-text-muted)", fontStyle: "italic" }}>
                      Valuation read not generated.
                    </p>
                  )}
                </Card>
              </div>

              {/* Financial Health — 4 horizontal percentile bars vs sector. */}
              <Card>
                <SectionLabel>Financial health · vs sector peers</SectionLabel>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                    gap: "22px",
                  }}
                >
                  <PercentileBar label="Revenue growth" value={fin.revenue_growth} percentile={pct.revenue_growth_percentile ?? fin.revenue_growth_score} />
                  <PercentileBar label="Profit margin"  value={fin.profit_margin}  percentile={pct.margin_percentile ?? fin.margin_score} />
                  <PercentileBar label="Return on equity" value={fin.roe} percentile={pct.roe_percentile ?? fin.roe_score} />
                  <PercentileBar label="Debt / equity"  value={fin.debt_to_equity} percentile={fin.debt_score != null ? 100 - fin.debt_score : null} invert />
                </div>
              </Card>

              {/* Key Risks + What to Watch — paired. */}
              <div className="responsive-grid-2" style={{ gap: "20px" }}>
                <Card>
                  <SectionLabel>Key risks</SectionLabel>
                  {deepDive.key_risks && deepDive.key_risks.length > 0 ? (
                    <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "12px" }}>
                      {deepDive.key_risks.map((r, i) => (
                        <li key={i} style={{ display: "grid", gridTemplateColumns: "14px 1fr", gap: "10px", alignItems: "flex-start" }} title={claimSource(r) || ""}>
                          <span style={{ fontFamily: MONO, fontSize: "12px", fontWeight: 700, color: "var(--color-accent-red)", lineHeight: 1.6 }}>!</span>
                          <span style={{ fontSize: "13.5px", color: "var(--color-text-secondary)", lineHeight: 1.55 }}>{claimText(r)}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p style={{ fontSize: "13px", color: "var(--color-text-muted)", fontStyle: "italic" }}>No stock-specific risks surfaced.</p>
                  )}
                </Card>

                <Card>
                  <SectionLabel>What to watch · concrete triggers</SectionLabel>
                  {deepDive.what_to_watch && deepDive.what_to_watch.length > 0 ? (
                    <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "14px" }}>
                      {deepDive.what_to_watch.map((w, i) => (
                        <li key={i} style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
                          <span style={{ fontFamily: MONO, fontSize: "12.5px", fontWeight: 700, color: "var(--color-text-primary)", letterSpacing: "0.01em" }}>
                            › {w.trigger}
                          </span>
                          <span style={{ fontSize: "12.5px", color: "var(--color-text-muted)", lineHeight: 1.5, paddingLeft: "14px" }}>{w.why}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p style={{ fontSize: "13px", color: "var(--color-text-muted)", fontStyle: "italic" }}>No actionable triggers identified.</p>
                  )}
                </Card>
              </div>

              {/* Catalysts — only render if non-empty. Editorial timeline. */}
              {deepDive.catalysts && deepDive.catalysts.length > 0 && (
                <Card>
                  <SectionLabel>Catalyst timeline</SectionLabel>
                  <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
                    {deepDive.catalysts.map((cat, i) => (
                      <div key={i} style={{ display: "flex", gap: "12px", alignItems: "flex-start" }}>
                        <div
                          style={{
                            width: "8px",
                            height: "8px",
                            borderRadius: "50%",
                            marginTop: "7px",
                            flexShrink: 0,
                            background: IMPACT_COLORS[cat.impact] || "var(--color-text-muted)",
                          }}
                        />
                        <div style={{ flex: 1 }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "10px" }}>
                            <span style={{ fontSize: "13.5px", fontWeight: 600, color: "var(--color-text-primary)" }}>{cat.title}</span>
                            <span
                              style={{
                                fontFamily: MONO,
                                fontSize: "10.5px",
                                fontWeight: 600,
                                letterSpacing: "0.08em",
                                textTransform: "uppercase",
                                padding: "2px 7px",
                                border: "1px solid var(--border-subtle)",
                                borderRadius: "4px",
                                color: "var(--color-text-muted)",
                                whiteSpace: "nowrap",
                              }}
                            >
                              {cat.timeline}
                            </span>
                          </div>
                          <p
                            title={claimSource(cat.description) || ""}
                            style={{ fontSize: "13px", color: "var(--color-text-secondary)", marginTop: "4px", lineHeight: 1.55 }}
                          >
                            {claimText(cat.description)}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>
              )}

              {/* Alternatives — same-sector peers with higher ROE. */}
              {deepDive.alternatives && deepDive.alternatives.length > 0 && (
                <Card>
                  <SectionLabel>Same-sector peers worth comparing</SectionLabel>
                  <div className="responsive-grid-2" style={{ gap: "14px" }}>
                    {deepDive.alternatives.map((alt, i) => (
                      <div
                        key={i}
                        onClick={() => { setTicker(alt.ticker); setSearchQuery(alt.ticker); setStockMeta(null); }}
                        style={{
                          padding: "14px 16px",
                          background: "var(--color-bg-secondary, transparent)",
                          border: "1px solid var(--border-subtle)",
                          borderRadius: "var(--radius-control)",
                          cursor: "pointer",
                          transition: "border-color 0.15s",
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.borderColor = "var(--border-strong)")}
                        onMouseLeave={(e) => (e.currentTarget.style.borderColor = "var(--border-subtle)")}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "4px" }}>
                          <span style={{ fontFamily: MONO, fontSize: "14px", fontWeight: 700, color: "var(--color-text-primary)" }}>{alt.ticker}</span>
                          <span
                            style={{
                              fontFamily: MONO,
                              fontSize: "10.5px",
                              fontWeight: 700,
                              color: "var(--color-accent-green)",
                              fontVariantNumeric: "tabular-nums",
                              letterSpacing: "0.04em",
                            }}
                          >
                            {alt.edge}
                          </span>
                        </div>
                        <p style={{ fontSize: "12.5px", color: "var(--color-text-muted)", margin: 0, marginBottom: "6px" }}>{alt.name}</p>
                        <p style={{ fontSize: "12.5px", color: "var(--color-text-secondary)", margin: 0, lineHeight: 1.5 }}>{claimText(alt.why)}</p>
                      </div>
                    ))}
                  </div>
                </Card>
              )}

              {/* Price chart */}
              <StockChart ticker={ticker} stockName={deepDive?.company || ticker} />

              {/* Data gaps — quiet footnote, only if any. */}
              {deepDive.data_gaps && deepDive.data_gaps.length > 0 && (
                <div
                  style={{
                    fontSize: "11.5px",
                    color: "var(--color-text-muted)",
                    fontFamily: MONO,
                    letterSpacing: "0.02em",
                    lineHeight: 1.6,
                    padding: "12px 16px",
                    border: "1px dashed var(--border-subtle)",
                    borderRadius: "var(--radius-control)",
                  }}
                >
                  <strong style={{ color: "var(--color-text-secondary)", letterSpacing: "0.1em" }}>DATA GAPS · </strong>
                  {deepDive.data_gaps.join(" · ")}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
