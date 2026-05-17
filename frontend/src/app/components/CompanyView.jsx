"use client";

/**
 * CompanyView — fundamentals + financials + peers + shareholding for a single
 * stock. Editorial-quiet rebuild.
 *
 * What changed from the old version:
 *   1. Routing bug — internal `ticker` state now syncs whenever the parent
 *      passes a new `ticker` prop (the old useState(initialTicker) only
 *      captured the prop on first mount, so clicking another stock from the
 *      portfolio reused the original ticker forever).
 *   2. UI — gradient hero, gradient avatar, gradient progress bars, glass-cards
 *      and emoji section headers (📈 💰 🚀 🏦 🧠) all removed. Now uses the
 *      same vocabulary as AnalysisView: hairlines, mono labels, serif italic
 *      for prose, single indigo accent, neutral outlined chips.
 *   3. Hero strip mirrors AnalysisView exactly so visiting Company → Deep Dive
 *      feels continuous (same mono ticker, 52w position dot, mcap chip).
 *   4. Loader — clean inline status while the 5 parallel REST calls resolve.
 */

import { useState, useEffect } from "react";
import StockChart from "./StockChart";
import { Skeleton } from "./Loaders";

import { API_BASE as _SHARED_API_BASE } from "../lib/api";
const API_BASE = _SHARED_API_BASE;

const SERIF = "var(--font-serif)";
const MONO  = "var(--font-mono)";

// ---------------------------------------------------------------------------
// Atoms
// ---------------------------------------------------------------------------

// BackButton — mirrors the one in AnalysisView so both detail pages share the
// same affordance. Accessibility: real <button>, aria-label includes the
// destination so screen readers say "Back to Portfolio" not just "Back".
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

function SectionLabel({ children, hint }) {
  return (
    <div style={{ marginBottom: "14px", display: "flex", alignItems: "baseline", gap: "12px" }}>
      <h4
        style={{
          fontSize: "10.5px",
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "0.18em",
          color: "var(--color-text-muted)",
          fontFamily: MONO,
          margin: 0,
        }}
      >
        {children}
      </h4>
      {hint && (
        <span style={{ fontSize: "11px", color: "var(--color-text-muted)" }}>· {hint}</span>
      )}
    </div>
  );
}

function Card({ children, style, ...rest }) {
  return (
    <div
      {...rest}
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

// Compact metric tile — replaces the old RatioCard with hover lift. Quieter,
// no animation, identical typography to other parts of the app.
function MetricTile({ label, value, subtitle, accent }) {
  return (
    <div
      style={{
        padding: "14px 16px",
        background: "var(--color-bg-card)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-control)",
      }}
    >
      <p
        style={{
          fontSize: "9.5px",
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "0.14em",
          color: "var(--color-text-muted)",
          marginBottom: "6px",
          fontFamily: MONO,
        }}
      >
        {label}
      </p>
      <p
        style={{
          fontSize: "17px",
          fontWeight: 700,
          fontVariantNumeric: "tabular-nums",
          fontFamily: MONO,
          color: accent || "var(--color-text-primary)",
          margin: 0,
          letterSpacing: "0.01em",
        }}
      >
        {value ?? "—"}
      </p>
      {subtitle && (
        <p style={{ fontSize: "10.5px", color: "var(--color-text-muted)", marginTop: "3px", fontFamily: MONO, letterSpacing: "0.04em" }}>
          {subtitle}
        </p>
      )}
    </div>
  );
}

// Editorial range bar — flat fill + small marker dot. No gradient. Same shape
// as the 52w-position widget in AnalysisView's hero so they read as one family.
function RangeBar({ low, current, high, label }) {
  if (!low || !high || !current) return null;
  const pct = Math.min(100, Math.max(0, ((current - low) / (high - low)) * 100));
  return (
    <div
      style={{
        padding: "14px 16px",
        background: "var(--color-bg-card)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-control)",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          marginBottom: "10px",
        }}
      >
        <span
          style={{
            fontSize: "9.5px",
            fontWeight: 700,
            color: "var(--color-text-muted)",
            textTransform: "uppercase",
            letterSpacing: "0.14em",
            fontFamily: MONO,
          }}
        >
          {label}
        </span>
        <span
          style={{
            color: "var(--color-text-primary)",
            fontSize: "12.5px",
            fontWeight: 700,
            fontFamily: MONO,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          ₹{current?.toLocaleString("en-IN")}
        </span>
      </div>
      <div style={{ position: "relative", height: "4px", borderRadius: "2px", background: "rgba(255,255,255,0.06)" }}>
        <div
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            height: "100%",
            width: `${pct}%`,
            borderRadius: "2px",
            background: "var(--color-accent-primary)",
            transition: "width 0.8s cubic-bezier(0.4, 0, 0.2, 1)",
            opacity: 0.55,
          }}
        />
        <div
          style={{
            position: "absolute",
            top: "-3px",
            left: `calc(${pct}% - 5px)`,
            width: "10px",
            height: "10px",
            borderRadius: "50%",
            background: "var(--color-accent-primary)",
            border: "2px solid var(--color-bg-card)",
          }}
        />
      </div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: "10.5px",
          color: "var(--color-text-muted)",
          marginTop: "8px",
          fontFamily: MONO,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        <span>₹{low?.toLocaleString("en-IN")}</span>
        <span>₹{high?.toLocaleString("en-IN")}</span>
      </div>
    </div>
  );
}

// Stat group — a key/value list for the ratio breakdown cards.
function StatList({ data, valueFmt }) {
  if (!data) return null;
  const entries = Object.entries(data).filter(([, v]) => v != null && v !== "—");
  if (entries.length === 0) {
    return <p style={{ fontSize: "12px", color: "var(--color-text-muted)", fontStyle: "italic", margin: 0 }}>No data</p>;
  }
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {entries.map(([k, v], i) => (
        <div
          key={k}
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
            padding: "8px 0",
            borderBottom: i === entries.length - 1 ? "none" : "1px solid var(--border-subtle)",
            fontSize: "12.5px",
          }}
        >
          <span style={{ color: "var(--color-text-muted)", textTransform: "capitalize", letterSpacing: "0.01em" }}>
            {k.replace(/_/g, " ")}
          </span>
          <span
            style={{
              fontWeight: 700,
              color: "var(--color-text-primary)",
              fontVariantNumeric: "tabular-nums",
              fontFamily: MONO,
            }}
          >
            {valueFmt ? valueFmt(v) : v ?? "—"}
          </span>
        </div>
      ))}
    </div>
  );
}

function FinancialTable({ data }) {
  if (!data || Object.keys(data).length === 0) {
    return (
      <p style={{ color: "var(--color-text-muted)", fontSize: "12.5px", padding: "20px", textAlign: "center", fontStyle: "italic" }}>
        No data available.
      </p>
    );
  }

  const periods = Object.keys(data);
  const allRows = new Set();
  periods.forEach((p) => Object.keys(data[p]).forEach((r) => allRows.add(r)));
  const rows = [...allRows].filter((r) => periods.some((p) => data[p][r] != null)).slice(0, 20);

  const fmtVal = (v) => {
    if (v == null) return "—";
    const cr = v / 1e7;
    if (Math.abs(cr) >= 1000) return `₹${(cr / 1000).toFixed(1)}K Cr`;
    if (Math.abs(cr) >= 1) return `₹${cr.toFixed(0)} Cr`;
    return `₹${(v / 1e5).toFixed(0)} L`;
  };

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12.5px" }}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--border-subtle)" }}>
            <th
              style={{
                padding: "10px 12px",
                textAlign: "left",
                fontWeight: 700,
                color: "var(--color-text-muted)",
                fontSize: "9.5px",
                textTransform: "uppercase",
                letterSpacing: "0.14em",
                position: "sticky",
                left: 0,
                background: "var(--color-bg-card)",
                minWidth: "180px",
                fontFamily: MONO,
              }}
            >
              Metric
            </th>
            {periods.map((p) => (
              <th
                key={p}
                style={{
                  padding: "10px 12px",
                  textAlign: "right",
                  fontWeight: 700,
                  color: "var(--color-text-muted)",
                  fontSize: "9.5px",
                  textTransform: "uppercase",
                  letterSpacing: "0.14em",
                  whiteSpace: "nowrap",
                  fontFamily: MONO,
                }}
              >
                {p.slice(0, 7)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={row}
              style={{
                borderBottom: "1px solid var(--border-subtle)",
                background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)",
              }}
            >
              <td
                style={{
                  padding: "9px 12px",
                  fontWeight: 500,
                  color: "var(--color-text-secondary)",
                  position: "sticky",
                  left: 0,
                  background: i % 2 === 0 ? "var(--color-bg-card)" : "var(--color-bg-card)",
                  fontSize: "12px",
                }}
              >
                {row.replace(/([A-Z])/g, " $1").trim()}
              </td>
              {periods.map((p) => (
                <td
                  key={p}
                  style={{
                    padding: "9px 12px",
                    textAlign: "right",
                    fontVariantNumeric: "tabular-nums",
                    color: "var(--color-text-primary)",
                    fontWeight: 500,
                    fontFamily: MONO,
                  }}
                >
                  {fmtVal(data[p][row])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatINR(n) {
  if (n == null || isNaN(n)) return "—";
  return `₹${Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
export default function CompanyView({ ticker: initialTicker, onNavigate, onBack, backLabel = "Back" }) {
  const [ticker, setTicker] = useState(initialTicker || "");
  const [searchQuery, setSearchQuery] = useState(initialTicker || "");
  const [searchResults, setSearchResults] = useState([]);
  const [showDropdown, setShowDropdown] = useState(false);

  const [overview, setOverview] = useState(null);
  const [ratios, setRatios] = useState(null);
  const [financials, setFinancials] = useState(null);
  const [peers, setPeers] = useState(null);
  const [shareholding, setShareholding] = useState(null);

  const [loading, setLoading] = useState(false);
  const [activeFinTab, setActiveFinTab] = useState("income_statement");
  const [finPeriod, setFinPeriod] = useState("annual");

  // Sync internal ticker when parent passes a new prop. Same fix as
  // AnalysisView — useState(initialTicker) only captures the first prop value,
  // so clicking another stock from PortfolioView would otherwise show stale
  // data from the original ticker.
  useEffect(() => {
    if (initialTicker && initialTicker !== ticker) {
      setTicker(initialTicker);
      setSearchQuery(initialTicker);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialTicker]);

  // Search dropdown
  const handleSearch = async (q) => {
    setSearchQuery(q);
    if (q.length < 2) { setSearchResults([]); setShowDropdown(false); return; }
    try {
      const res = await fetch(`${API_BASE}/api/stocks/search?q=${q}&limit=8`);
      setSearchResults(await res.json());
      setShowDropdown(true);
    } catch { setSearchResults([]); }
  };

  const selectStock = (stock) => {
    setTicker(stock.ticker);
    setSearchQuery(stock.ticker);
    setShowDropdown(false);
    setSearchResults([]);
  };

  // Fetch all data when ticker changes
  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    setOverview(null); setRatios(null); setFinancials(null); setPeers(null); setShareholding(null);

    Promise.all([
      fetch(`${API_BASE}/api/company/${ticker}/overview`).then((r) => r.json()).catch(() => null),
      fetch(`${API_BASE}/api/company/${ticker}/ratios`).then((r) => r.json()).catch(() => null),
      fetch(`${API_BASE}/api/company/${ticker}/financials?period=${finPeriod}`).then((r) => r.json()).catch(() => null),
      fetch(`${API_BASE}/api/company/${ticker}/peers`).then((r) => r.json()).catch(() => null),
      fetch(`${API_BASE}/api/company/${ticker}/shareholding`).then((r) => r.json()).catch(() => null),
    ]).then(([ov, rat, fin, pe, sh]) => {
      setOverview(ov);
      setRatios(rat);
      setFinancials(fin);
      setPeers(pe);
      setShareholding(sh);
      setLoading(false);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker]);

  // Refetch financials when period toggles
  useEffect(() => {
    if (!ticker) return;
    fetch(`${API_BASE}/api/company/${ticker}/financials?period=${finPeriod}`)
      .then((r) => r.json())
      .then(setFinancials)
      .catch(() => {});
  }, [finPeriod, ticker]);

  const isPos = (overview?.change_percent ?? 0) >= 0;

  // 52w position (single dot, mirrors AnalysisView hero)
  let band52w = null;
  if (overview?.current_price && overview?.high_52w && overview?.low_52w && overview.high_52w > overview.low_52w) {
    band52w = Math.round(((overview.current_price - overview.low_52w) / (overview.high_52w - overview.low_52w)) * 100);
  }

  return (
    <div>
      {/* Back button — only renders when we have somewhere to go back to. */}
      {onBack && <BackButton onBack={onBack} label={backLabel} />}

      {/* Header */}
      <div style={{ marginBottom: "24px" }}>
        <h2
          style={{
            fontSize: "22px",
            fontWeight: 700,
            color: "var(--color-text-primary)",
            letterSpacing: "-0.01em",
          }}
        >
          Company details
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
          Fundamentals, ratios, statements, peers & shareholding.
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
            style={{ position: "absolute", left: "14px", top: "50%", transform: "translateY(-50%)", width: "16px", height: "16px", color: "var(--color-text-muted)" }}
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
              Fundamentals · awaiting ticker
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
              You&rsquo;ll see live ratios, the last few years of income / balance / cash-flow,
              peer comparison and the shareholding pattern — all on one page.
            </p>
          </div>
        </Card>
      )}

      {/* Loading */}
      {loading && ticker && (
        <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              padding: "14px 18px",
              background: "var(--color-bg-card)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--radius-control)",
            }}
          >
            <span
              style={{
                width: "8px",
                height: "8px",
                borderRadius: "50%",
                background: "var(--color-accent-primary)",
                animation: "cv-pulse 1.6s ease-in-out infinite",
              }}
            />
            <span
              style={{
                fontFamily: MONO,
                fontSize: "11px",
                fontWeight: 700,
                letterSpacing: "0.14em",
                textTransform: "uppercase",
                color: "var(--color-text-secondary)",
              }}
            >
              Loading {ticker} · fundamentals + statements + peers
            </span>
          </div>
          <Skeleton h={110} r={12} />
          <Skeleton h={150} r={12} />
          <Skeleton h={220} r={12} />
          <style jsx>{`
            @keyframes cv-pulse {
              0%, 100% { opacity: 1; transform: scale(1); }
              50%      { opacity: 0.4; transform: scale(1.4); }
            }
          `}</style>
        </div>
      )}

      {/* Content */}
      {!loading && overview && (
        <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>

          {/* HERO STRIP — mirrors AnalysisView for visual continuity */}
          <Card
            style={{
              padding: "18px 22px",
              display: "flex",
              alignItems: "center",
              gap: "20px",
              flexWrap: "wrap",
              borderLeft: `3px solid ${isPos ? "var(--color-accent-green)" : "var(--color-accent-red)"}`,
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
                {overview.sector && (
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
                    {overview.sector}
                  </span>
                )}
              </div>
              <span style={{ fontSize: "13px", color: "var(--color-text-muted)", marginTop: "3px" }}>
                {overview.name}
              </span>
              {overview.industry && overview.industry !== "—" && (
                <span style={{ fontSize: "11px", color: "var(--color-text-muted)", marginTop: "2px", fontFamily: MONO, letterSpacing: "0.02em" }}>
                  {overview.industry}
                </span>
              )}
            </div>

            {overview.current_price > 0 && (
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
                    {formatINR(overview.current_price)}
                  </span>
                  {overview.change_percent != null && (
                    <span
                      style={{
                        fontSize: "12.5px",
                        fontWeight: 700,
                        fontFamily: MONO,
                        color: isPos ? "var(--color-accent-green)" : "var(--color-accent-red)",
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      {isPos ? "▲ +" : "▼ "}{Math.abs(overview.change_percent).toFixed(2)}%
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

            {overview.market_cap_formatted && (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", lineHeight: 1.15 }}>
                <span style={{ fontFamily: MONO, fontSize: "9.5px", letterSpacing: "0.16em", textTransform: "uppercase", color: "var(--color-text-muted)", fontWeight: 700 }}>Mcap</span>
                <span style={{ fontFamily: MONO, fontSize: "13px", fontWeight: 700, color: "var(--color-text-primary)", marginTop: "4px", fontVariantNumeric: "tabular-nums" }}>
                  {overview.market_cap_formatted}
                </span>
              </div>
            )}

            <div style={{ marginLeft: "auto" }}>
              <button
                onClick={() => onNavigate?.("analysis", ticker)}
                style={{
                  padding: "8px 14px",
                  borderRadius: "var(--radius-control)",
                  fontSize: "11px",
                  fontWeight: 700,
                  letterSpacing: "0.06em",
                  border: "1px solid var(--color-accent-primary)",
                  background: "var(--color-accent-primary)",
                  color: "#fff",
                  cursor: "pointer",
                  fontFamily: MONO,
                  textTransform: "uppercase",
                }}
              >
                Run AI deep dive →
              </button>
            </div>
          </Card>

          {/* DESCRIPTION — only if there is one */}
          {overview.description && (
            <Card style={{ padding: "22px 28px" }}>
              <SectionLabel>About the business</SectionLabel>
              <p
                style={{
                  fontFamily: SERIF,
                  fontSize: "15px",
                  lineHeight: 1.65,
                  color: "var(--color-text-secondary)",
                  margin: 0,
                  letterSpacing: "-0.003em",
                }}
              >
                {overview.description}
              </p>
            </Card>
          )}

          {/* RANGES */}
          {(overview.low_52w || overview.day_low) && (
            <div className="responsive-grid-2" style={{ gap: "14px" }}>
              <RangeBar low={overview.low_52w} current={overview.current_price} high={overview.high_52w} label="52 week range" />
              <RangeBar low={overview.day_low} current={overview.current_price} high={overview.day_high} label="Day range" />
            </div>
          )}

          {/* KEY RATIOS */}
          <Card>
            <SectionLabel>Key ratios</SectionLabel>
            <div className="responsive-grid-4" style={{ gap: "10px" }}>
              <MetricTile label="P/E ratio" value={overview.pe_ratio} subtitle="Trailing TTM" />
              <MetricTile label="P/B ratio" value={overview.pb_ratio} subtitle="Price to book" />
              <MetricTile label="EPS" value={overview.eps ? `₹${overview.eps}` : null} subtitle="Earnings / share" />
              <MetricTile
                label="ROE"
                value={overview.roe ? `${overview.roe}%` : null}
                subtitle="Return on equity"
                accent={overview.roe > 15 ? "var(--color-accent-green)" : undefined}
              />
              <MetricTile
                label="Debt / equity"
                value={overview.debt_to_equity}
                subtitle="Leverage"
                accent={overview.debt_to_equity > 100 ? "var(--color-accent-red)" : undefined}
              />
              <MetricTile label="Dividend yield" value={overview.dividend_yield ? `${overview.dividend_yield}%` : null} subtitle="Annual" />
              <MetricTile label="Book value" value={overview.book_value ? `₹${overview.book_value}` : null} subtitle="Per share" />
              <MetricTile label="Volume" value={overview.volume?.toLocaleString("en-IN")} subtitle="Today" />
            </div>
          </Card>

          {/* DETAILED RATIOS */}
          {ratios && (
            <div className="responsive-grid-4" style={{ gap: "14px" }}>
              <Card style={{ padding: "18px 20px" }}>
                <SectionLabel>Valuation</SectionLabel>
                <StatList data={ratios.valuation} />
              </Card>
              <Card style={{ padding: "18px 20px" }}>
                <SectionLabel>Profitability</SectionLabel>
                <StatList
                  data={ratios.profitability}
                  valueFmt={(v) => (typeof v === "number" ? `${v}%` : v)}
                />
              </Card>
              <Card style={{ padding: "18px 20px" }}>
                <SectionLabel>Growth</SectionLabel>
                <StatList
                  data={ratios.growth}
                  valueFmt={(v) => (typeof v === "number" ? `${v}%` : v)}
                />
              </Card>
              <Card style={{ padding: "18px 20px" }}>
                <SectionLabel>Financial health</SectionLabel>
                <StatList data={ratios.financial_health} />
              </Card>
            </div>
          )}

          {/* PRICE CHART */}
          <StockChart ticker={ticker} stockName={overview.name} />

          {/* FINANCIAL STATEMENTS */}
          <Card style={{ padding: 0, overflow: "hidden" }}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "14px 20px",
                borderBottom: "1px solid var(--border-subtle)",
                gap: "12px",
                flexWrap: "wrap",
              }}
            >
              <div style={{ display: "flex", gap: "4px" }}>
                {[
                  { id: "income_statement", label: "Income" },
                  { id: "balance_sheet",    label: "Balance" },
                  { id: "cash_flow",        label: "Cash flow" },
                ].map((tab) => {
                  const on = activeFinTab === tab.id;
                  return (
                    <button
                      key={tab.id}
                      onClick={() => setActiveFinTab(tab.id)}
                      style={{
                        padding: "7px 13px",
                        borderRadius: "var(--radius-control)",
                        fontSize: "11.5px",
                        fontWeight: 700,
                        letterSpacing: "0.06em",
                        textTransform: "uppercase",
                        border: "1px solid",
                        borderColor: on ? "var(--color-accent-primary)" : "var(--border-subtle)",
                        cursor: "pointer",
                        background: on ? "color-mix(in srgb, var(--color-accent-primary) 12%, transparent)" : "transparent",
                        color: on ? "var(--color-accent-primary)" : "var(--color-text-muted)",
                        fontFamily: MONO,
                      }}
                    >
                      {tab.label}
                    </button>
                  );
                })}
              </div>
              <div style={{ display: "flex", gap: "4px" }}>
                {["annual", "quarterly"].map((p) => {
                  const on = finPeriod === p;
                  return (
                    <button
                      key={p}
                      onClick={() => setFinPeriod(p)}
                      style={{
                        padding: "6px 11px",
                        borderRadius: "var(--radius-control)",
                        fontSize: "10.5px",
                        fontWeight: 700,
                        letterSpacing: "0.08em",
                        textTransform: "uppercase",
                        border: "1px solid",
                        borderColor: on ? "var(--border-strong)" : "var(--border-subtle)",
                        cursor: "pointer",
                        background: "transparent",
                        color: on ? "var(--color-text-primary)" : "var(--color-text-muted)",
                        fontFamily: MONO,
                      }}
                    >
                      {p}
                    </button>
                  );
                })}
              </div>
            </div>
            <div style={{ padding: "4px" }}>
              <FinancialTable data={financials?.[activeFinTab]} />
            </div>
          </Card>

          {/* PEER COMPARISON */}
          {peers && peers.peers?.length > 0 && (
            <Card style={{ padding: 0, overflow: "hidden" }}>
              <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border-subtle)" }}>
                <SectionLabel hint={peers.sector}>Peer comparison</SectionLabel>
              </div>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12.5px" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                      {["Company", "Price", "Mkt Cap", "P/E", "P/B", "ROE", "Margin", "D/E", "Div%"].map((h) => (
                        <th
                          key={h}
                          style={{
                            padding: "12px 14px",
                            textAlign: h === "Company" ? "left" : "right",
                            fontWeight: 700,
                            color: "var(--color-text-muted)",
                            fontSize: "9.5px",
                            textTransform: "uppercase",
                            letterSpacing: "0.14em",
                            fontFamily: MONO,
                          }}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {peers.peers.map((p, i) => (
                      <tr
                        key={p.ticker}
                        style={{
                          borderBottom: "1px solid var(--border-subtle)",
                          background: p.is_target
                            ? "color-mix(in srgb, var(--color-accent-primary) 6%, transparent)"
                            : i % 2 === 0
                            ? "transparent"
                            : "rgba(255,255,255,0.015)",
                          cursor: p.is_target ? "default" : "pointer",
                        }}
                        onClick={() => { if (!p.is_target) { setTicker(p.ticker); setSearchQuery(p.ticker); } }}
                        onMouseEnter={(e) => { if (!p.is_target) e.currentTarget.style.background = "var(--color-bg-card-hover, rgba(255,255,255,0.03))"; }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.background = p.is_target
                            ? "color-mix(in srgb, var(--color-accent-primary) 6%, transparent)"
                            : i % 2 === 0
                            ? "transparent"
                            : "rgba(255,255,255,0.015)";
                        }}
                      >
                        <td style={{ padding: "12px 14px" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                            {p.is_target && (
                              <span style={{ width: "3px", height: "18px", borderRadius: "2px", background: "var(--color-accent-primary)" }} />
                            )}
                            <div>
                              <span style={{ fontWeight: p.is_target ? 800 : 700, color: "var(--color-text-primary)", fontFamily: MONO }}>{p.ticker}</span>
                              <div style={{ fontSize: "10.5px", color: "var(--color-text-muted)", marginTop: "1px" }}>{p.name?.slice(0, 28)}</div>
                            </div>
                          </div>
                        </td>
                        <td style={{ padding: "12px 14px", textAlign: "right", fontWeight: 700, fontVariantNumeric: "tabular-nums", color: "var(--color-text-primary)", fontFamily: MONO }}>₹{p.current_price?.toLocaleString("en-IN")}</td>
                        <td style={{ padding: "12px 14px", textAlign: "right", color: "var(--color-text-secondary)", fontVariantNumeric: "tabular-nums", fontFamily: MONO }}>{p.market_cap}</td>
                        <td style={{ padding: "12px 14px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: "var(--color-text-primary)", fontFamily: MONO }}>{p.pe_ratio ?? "—"}</td>
                        <td style={{ padding: "12px 14px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: "var(--color-text-primary)", fontFamily: MONO }}>{p.pb_ratio ?? "—"}</td>
                        <td style={{ padding: "12px 14px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: p.roe > 15 ? "var(--color-accent-green)" : "var(--color-text-primary)", fontFamily: MONO }}>{p.roe != null ? `${p.roe}%` : "—"}</td>
                        <td style={{ padding: "12px 14px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: "var(--color-text-primary)", fontFamily: MONO }}>{p.profit_margin != null ? `${p.profit_margin}%` : "—"}</td>
                        <td style={{ padding: "12px 14px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: p.debt_to_equity > 100 ? "var(--color-accent-red)" : "var(--color-text-primary)", fontFamily: MONO }}>{p.debt_to_equity ?? "—"}</td>
                        <td style={{ padding: "12px 14px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: "var(--color-text-primary)", fontFamily: MONO }}>{p.dividend_yield != null ? `${p.dividend_yield}%` : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {/* SHAREHOLDING */}
          {shareholding && (shareholding.major_holders?.length > 0 || shareholding.top_institutions?.length > 0) && (
            <div className="responsive-grid-2" style={{ gap: "14px" }}>
              {shareholding.major_holders?.length > 0 && (
                <Card>
                  <SectionLabel>Shareholding pattern</SectionLabel>
                  <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                    {shareholding.major_holders.map((h, i) => {
                      const pct = parseFloat(h.value);
                      return (
                        <div key={i}>
                          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12.5px", marginBottom: "6px" }}>
                            <span style={{ color: "var(--color-text-secondary)" }}>{h.label}</span>
                            <span style={{ fontWeight: 700, color: "var(--color-text-primary)", fontFamily: MONO, fontVariantNumeric: "tabular-nums" }}>{h.value}</span>
                          </div>
                          {!isNaN(pct) && (
                            <div style={{ height: "3px", borderRadius: "2px", background: "rgba(255,255,255,0.06)", overflow: "hidden" }}>
                              <div
                                style={{
                                  height: "100%",
                                  width: `${Math.min(pct, 100)}%`,
                                  borderRadius: "2px",
                                  background: "var(--color-accent-primary)",
                                  opacity: 0.7,
                                  transition: "width 0.8s ease",
                                }}
                              />
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </Card>
              )}

              {shareholding.top_institutions?.length > 0 && (
                <Card>
                  <SectionLabel>Top institutional holders</SectionLabel>
                  <div style={{ display: "flex", flexDirection: "column" }}>
                    {shareholding.top_institutions.map((inst, i) => (
                      <div
                        key={i}
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          padding: "9px 0",
                          borderBottom: i === shareholding.top_institutions.length - 1 ? "none" : "1px solid var(--border-subtle)",
                          fontSize: "12.5px",
                        }}
                      >
                        <span style={{ color: "var(--color-text-secondary)", flex: 1 }}>{inst.holder}</span>
                        <span
                          style={{
                            fontWeight: 700,
                            color: "var(--color-text-primary)",
                            fontVariantNumeric: "tabular-nums",
                            marginLeft: "12px",
                            fontFamily: MONO,
                          }}
                        >
                          {inst.pct_out ? `${inst.pct_out}%` : `${(inst.shares / 1e7).toFixed(1)}Cr shares`}
                        </span>
                      </div>
                    ))}
                  </div>
                </Card>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
