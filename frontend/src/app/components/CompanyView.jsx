"use client";

import { useState, useEffect, useCallback } from "react";
import StockChart from "./StockChart";

import { API_BASE as _SHARED_API_BASE } from "../lib/api";
const API_BASE = _SHARED_API_BASE;

// -----------------------------------------------------------------------
// Sub-components
// -----------------------------------------------------------------------
function RatioCard({ label, value, subtitle, color }) {
  return (
    <div style={{
      padding: "16px", borderRadius: "14px",
      background: "var(--color-bg-card)", border: "1px solid var(--border-subtle)",
      transition: "all 0.2s",
    }}
      onMouseEnter={(e) => { e.currentTarget.style.borderColor = "var(--color-accent-primary)"; e.currentTarget.style.transform = "translateY(-2px)"; }}
      onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--border-subtle)"; e.currentTarget.style.transform = "translateY(0)"; }}
    >
      <p style={{ fontSize: "10px", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--color-text-muted)", marginBottom: "6px" }}>{label}</p>
      <p style={{ fontSize: "20px", fontWeight: 800, fontVariantNumeric: "tabular-nums", color: color || "var(--color-text-primary)" }}>
        {value ?? "—"}
      </p>
      {subtitle && <p style={{ fontSize: "11px", color: "var(--color-text-muted)", marginTop: "2px" }}>{subtitle}</p>}
    </div>
  );
}

function RangeBar({ low, current, high, label }) {
  if (!low || !high || !current) return null;
  const pct = Math.min(100, Math.max(0, ((current - low) / (high - low)) * 100));
  return (
    <div style={{ padding: "14px 16px", borderRadius: "12px", background: "var(--color-bg-card)", border: "1px solid var(--border-subtle)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "10px", fontWeight: 600, color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: "8px" }}>
        <span>{label}</span>
        <span style={{ color: "var(--color-text-primary)", fontSize: "13px", fontWeight: 700 }}>₹{current?.toLocaleString("en-IN")}</span>
      </div>
      <div style={{ position: "relative", height: "6px", borderRadius: "3px", background: "rgba(148,163,184,0.12)" }}>
        <div style={{ position: "absolute", left: 0, top: 0, height: "100%", width: `${pct}%`, borderRadius: "3px", background: "linear-gradient(90deg, var(--color-accent-primary), var(--color-accent-cyan))", transition: "width 0.8s ease-out" }} />
        <div style={{ position: "absolute", top: "-3px", left: `${pct}%`, transform: "translateX(-50%)", width: "12px", height: "12px", borderRadius: "50%", background: "var(--color-accent-primary)", border: "2px solid var(--color-bg-card)" }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", color: "var(--color-text-muted)", marginTop: "6px", fontVariantNumeric: "tabular-nums" }}>
        <span>₹{low?.toLocaleString("en-IN")}</span>
        <span>₹{high?.toLocaleString("en-IN")}</span>
      </div>
    </div>
  );
}

function FinancialTable({ data, title }) {
  if (!data || Object.keys(data).length === 0) return <p style={{ color: "var(--color-text-muted)", fontSize: "13px", padding: "20px", textAlign: "center" }}>No data available</p>;

  const periods = Object.keys(data);
  const allRows = new Set();
  periods.forEach((p) => Object.keys(data[p]).forEach((r) => allRows.add(r)));
  const rows = [...allRows].filter((r) => {
    // Filter out rows that are all null
    return periods.some((p) => data[p][r] != null);
  }).slice(0, 20); // Limit to 20 most important rows

  const fmtVal = (v) => {
    if (v == null) return "—";
    const cr = v / 1e7;
    if (Math.abs(cr) >= 1000) return `₹${(cr / 1000).toFixed(1)}K Cr`;
    if (Math.abs(cr) >= 1) return `₹${cr.toFixed(0)} Cr`;
    return `₹${(v / 1e5).toFixed(0)} L`;
  };

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--border-subtle)" }}>
            <th style={{ padding: "10px 12px", textAlign: "left", fontWeight: 600, color: "var(--color-text-muted)", fontSize: "10px", textTransform: "uppercase", letterSpacing: "0.05em", position: "sticky", left: 0, background: "var(--color-bg-card)", minWidth: "180px" }}>Metric</th>
            {periods.map((p) => (
              <th key={p} style={{ padding: "10px 12px", textAlign: "right", fontWeight: 600, color: "var(--color-text-muted)", fontSize: "10px", textTransform: "uppercase", letterSpacing: "0.05em", whiteSpace: "nowrap" }}>
                {p.slice(0, 7)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={row} style={{ borderBottom: "1px solid var(--border-subtle)", background: i % 2 === 0 ? "transparent" : "rgba(99,102,241,0.02)" }}>
              <td style={{ padding: "8px 12px", fontWeight: 500, color: "var(--color-text-secondary)", position: "sticky", left: 0, background: i % 2 === 0 ? "var(--color-bg-card)" : "var(--color-bg-card)", fontSize: "11px" }}>
                {row.replace(/([A-Z])/g, " $1").trim()}
              </td>
              {periods.map((p) => (
                <td key={p} style={{ padding: "8px 12px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: "var(--color-text-primary)", fontWeight: 500 }}>
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

// -----------------------------------------------------------------------
// Main Component
// -----------------------------------------------------------------------
export default function CompanyView({ ticker: initialTicker, onNavigate }) {
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

  // Search
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
      fetch(`${API_BASE}/api/company/${ticker}/overview`).then(r => r.json()).catch(() => null),
      fetch(`${API_BASE}/api/company/${ticker}/ratios`).then(r => r.json()).catch(() => null),
      fetch(`${API_BASE}/api/company/${ticker}/financials?period=${finPeriod}`).then(r => r.json()).catch(() => null),
      fetch(`${API_BASE}/api/company/${ticker}/peers`).then(r => r.json()).catch(() => null),
      fetch(`${API_BASE}/api/company/${ticker}/shareholding`).then(r => r.json()).catch(() => null),
    ]).then(([ov, rat, fin, pe, sh]) => {
      setOverview(ov);
      setRatios(rat);
      setFinancials(fin);
      setPeers(pe);
      setShareholding(sh);
      setLoading(false);
    });
  }, [ticker]);

  // Refetch financials when period changes
  useEffect(() => {
    if (!ticker) return;
    fetch(`${API_BASE}/api/company/${ticker}/financials?period=${finPeriod}`)
      .then(r => r.json())
      .then(setFinancials)
      .catch(() => {});
  }, [finPeriod, ticker]);

  const isPos = (overview?.change_percent ?? 0) >= 0;

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: "24px" }}>
        <h2 style={{ fontSize: "24px", fontWeight: 700, color: "var(--color-text-primary)" }}>Company Details</h2>
        <p style={{ fontSize: "13px", color: "var(--color-text-muted)", marginTop: "4px" }}>
          Financial data, ratios, peer comparison & analysis
        </p>
      </div>

      {/* Stock Search */}
      <div style={{ marginBottom: "24px", position: "relative", maxWidth: "500px" }}>
        <div style={{ position: "relative" }}>
          <input type="text" placeholder="Search for a stock (e.g. RELIANCE, TCS)..."
            value={searchQuery}
            onChange={(e) => handleSearch(e.target.value)}
            onFocus={() => { if (searchResults.length) setShowDropdown(true); }}
            style={{ width: "100%", padding: "14px 20px 14px 44px", borderRadius: "14px", fontSize: "14px", border: "1px solid var(--border-subtle)", outline: "none", background: "var(--color-bg-card)", color: "var(--color-text-primary)" }}
          />
          <svg style={{ position: "absolute", left: "16px", top: "50%", transform: "translateY(-50%)", width: "18px", height: "18px", color: "var(--color-text-muted)" }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>

        {showDropdown && searchResults.length > 0 && (
          <div style={{ position: "absolute", top: "100%", left: 0, right: 0, marginTop: "6px", zIndex: 20, background: "var(--color-bg-card)", border: "1px solid var(--border-subtle)", borderRadius: "12px", overflow: "hidden", boxShadow: "0 8px 24px rgba(0,0,0,0.4)" }}>
            {searchResults.map((s) => (
              <div key={s.ticker} onClick={() => selectStock(s)}
                style={{ padding: "12px 16px", cursor: "pointer", borderBottom: "1px solid var(--border-subtle)", display: "flex", justifyContent: "space-between", alignItems: "center" }}
                onMouseEnter={(e) => e.currentTarget.style.background = "rgba(99,102,241,0.08)"}
                onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}
              >
                <div>
                  <span style={{ fontWeight: 600, fontSize: "14px", color: "var(--color-text-primary)" }}>{s.ticker}</span>
                  <span style={{ color: "var(--color-text-muted)", marginLeft: "10px", fontSize: "13px" }}>{s.name}</span>
                </div>
                <span style={{ padding: "2px 8px", borderRadius: "4px", fontSize: "10px", fontWeight: 500, background: "rgba(99,102,241,0.1)", color: "var(--color-accent-secondary)" }}>{s.sector}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Empty State */}
      {!ticker && (
        <div className="glass-card" style={{ padding: "80px 24px", textAlign: "center", background: "linear-gradient(135deg, rgba(99,102,241,0.05), rgba(6,182,212,0.03))" }}>
          <span style={{ fontSize: "56px", display: "block", marginBottom: "16px" }}>📊</span>
          <p style={{ fontSize: "18px", fontWeight: 700, color: "var(--color-text-primary)" }}>Search for a company</p>
          <p style={{ fontSize: "14px", color: "var(--color-text-muted)", marginTop: "8px", maxWidth: "400px", margin: "8px auto 0" }}>
            View key ratios, financial statements, peer comparison, shareholding patterns
          </p>
        </div>
      )}

      {/* Loading */}
      {loading && ticker && (
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          {[1, 2, 3].map((i) => <div key={i} className="shimmer" style={{ height: "120px", borderRadius: "16px" }} />)}
        </div>
      )}

      {/* Content */}
      {!loading && overview && (
        <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>

          {/* =============== HERO =============== */}
          <div className="glass-card" style={{ padding: "24px", background: "linear-gradient(135deg, rgba(99,102,241,0.06), rgba(6,182,212,0.04))" }}>
            <div style={{ display: "flex", alignItems: "flex-start", gap: "20px", flexWrap: "wrap" }}>
              {/* Left: Name + Badge */}
              <div style={{ flex: 1, minWidth: "280px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "14px", marginBottom: "8px" }}>
                  <div style={{ width: "52px", height: "52px", borderRadius: "14px", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: "22px", color: "white", background: "linear-gradient(135deg, var(--color-accent-primary), var(--color-accent-cyan))", flexShrink: 0 }}>
                    {ticker.charAt(0)}
                  </div>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span style={{ fontSize: "22px", fontWeight: 800, color: "var(--color-text-primary)" }}>{ticker}</span>
                      <span style={{ padding: "3px 10px", borderRadius: "6px", fontSize: "11px", fontWeight: 600, background: "rgba(99,102,241,0.12)", color: "var(--color-accent-secondary)" }}>{overview.sector}</span>
                    </div>
                    <p style={{ fontSize: "14px", color: "var(--color-text-muted)", marginTop: "2px" }}>{overview.name}</p>
                  </div>
                </div>
                {overview.industry !== "—" && (
                  <p style={{ fontSize: "12px", color: "var(--color-text-muted)", marginTop: "4px" }}>
                    Industry: <span style={{ color: "var(--color-text-secondary)" }}>{overview.industry}</span>
                  </p>
                )}
                {overview.description && (
                  <p style={{ fontSize: "12px", color: "var(--color-text-muted)", lineHeight: 1.6, marginTop: "10px", maxWidth: "500px" }}>
                    {overview.description}
                  </p>
                )}
              </div>

              {/* Right: Price */}
              <div style={{ textAlign: "right", minWidth: "180px" }}>
                <p style={{ fontSize: "32px", fontWeight: 800, fontVariantNumeric: "tabular-nums", color: "var(--color-text-primary)" }}>
                  ₹{overview.current_price?.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </p>
                <p style={{ fontSize: "16px", fontWeight: 700, fontVariantNumeric: "tabular-nums", color: isPos ? "var(--color-accent-green)" : "var(--color-accent-red)", marginTop: "4px" }}>
                  {isPos ? "▲ +" : "▼ "}{overview.change_percent?.toFixed(2)}%
                </p>
                <p style={{ fontSize: "12px", color: "var(--color-text-muted)", marginTop: "4px" }}>
                  Mkt Cap: <span style={{ fontWeight: 600, color: "var(--color-text-secondary)" }}>{overview.market_cap_formatted}</span>
                </p>
              </div>
            </div>

            {/* 52W Range + Day Range */}
            <div className="responsive-grid-2" style={{ marginTop: "20px" }}>
              <RangeBar low={overview.low_52w} current={overview.current_price} high={overview.high_52w} label="52 Week Range" />
              <RangeBar low={overview.day_low} current={overview.current_price} high={overview.day_high} label="Day Range" />
            </div>
          </div>

          {/* =============== KEY RATIOS =============== */}
          <div>
            <h3 style={{ fontSize: "13px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--color-text-muted)", marginBottom: "12px" }}>Key Ratios</h3>
            <div className="responsive-grid-4" style={{ gap: "10px" }}>
              <RatioCard label="P/E Ratio" value={overview.pe_ratio} subtitle="Trailing TTM" />
              <RatioCard label="P/B Ratio" value={overview.pb_ratio} subtitle="Price to Book" />
              <RatioCard label="EPS" value={overview.eps ? `₹${overview.eps}` : null} subtitle="Earnings/Share" />
              <RatioCard label="ROE" value={overview.roe ? `${overview.roe}%` : null} subtitle="Return on Equity" color={overview.roe > 15 ? "var(--color-accent-green)" : undefined} />
              <RatioCard label="Debt/Equity" value={overview.debt_to_equity} subtitle="Leverage" color={overview.debt_to_equity > 100 ? "var(--color-accent-red)" : undefined} />
              <RatioCard label="Div Yield" value={overview.dividend_yield ? `${overview.dividend_yield}%` : null} subtitle="Annual" />
              <RatioCard label="Book Value" value={overview.book_value ? `₹${overview.book_value}` : null} subtitle="Per Share" />
              <RatioCard label="Volume" value={overview.volume?.toLocaleString("en-IN")} subtitle="Today" />
            </div>
          </div>

          {/* =============== DETAILED RATIOS =============== */}
          {ratios && (
            <div>
              <h3 style={{ fontSize: "13px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--color-text-muted)", marginBottom: "12px" }}>Detailed Analysis</h3>
              <div className="responsive-grid-4" style={{ gap: "16px" }}>
                {/* Valuation */}
                <div className="glass-card" style={{ padding: "18px" }}>
                  <h4 style={{ fontSize: "11px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--color-accent-primary)", marginBottom: "12px" }}>📈 Valuation</h4>
                  {Object.entries(ratios.valuation || {}).map(([k, v]) => (
                    <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--border-subtle)", fontSize: "12px" }}>
                      <span style={{ color: "var(--color-text-muted)", textTransform: "capitalize" }}>{k.replace(/_/g, " ")}</span>
                      <span style={{ fontWeight: 600, color: "var(--color-text-primary)", fontVariantNumeric: "tabular-nums" }}>{v ?? "—"}</span>
                    </div>
                  ))}
                </div>
                {/* Profitability */}
                <div className="glass-card" style={{ padding: "18px" }}>
                  <h4 style={{ fontSize: "11px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--color-accent-green)", marginBottom: "12px" }}>💰 Profitability</h4>
                  {Object.entries(ratios.profitability || {}).map(([k, v]) => (
                    <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--border-subtle)", fontSize: "12px" }}>
                      <span style={{ color: "var(--color-text-muted)", textTransform: "capitalize" }}>{k.replace(/_/g, " ")}</span>
                      <span style={{ fontWeight: 600, color: "var(--color-text-primary)" }}>{v != null ? (typeof v === "number" ? `${v}%` : v) : "—"}</span>
                    </div>
                  ))}
                </div>
                {/* Growth */}
                <div className="glass-card" style={{ padding: "18px" }}>
                  <h4 style={{ fontSize: "11px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--color-accent-cyan)", marginBottom: "12px" }}>🚀 Growth</h4>
                  {Object.entries(ratios.growth || {}).map(([k, v]) => (
                    <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--border-subtle)", fontSize: "12px" }}>
                      <span style={{ color: "var(--color-text-muted)", textTransform: "capitalize" }}>{k.replace(/_/g, " ")}</span>
                      <span style={{ fontWeight: 600, color: v > 0 ? "var(--color-accent-green)" : v < 0 ? "var(--color-accent-red)" : "var(--color-text-primary)" }}>{v != null ? `${v}%` : "—"}</span>
                    </div>
                  ))}
                </div>
                {/* Financial Health */}
                <div className="glass-card" style={{ padding: "18px" }}>
                  <h4 style={{ fontSize: "11px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--color-accent-amber)", marginBottom: "12px" }}>🏦 Health</h4>
                  {Object.entries(ratios.financial_health || {}).map(([k, v]) => (
                    <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--border-subtle)", fontSize: "12px" }}>
                      <span style={{ color: "var(--color-text-muted)", textTransform: "capitalize" }}>{k.replace(/_/g, " ")}</span>
                      <span style={{ fontWeight: 600, color: "var(--color-text-primary)" }}>{v ?? "—"}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* =============== PRICE CHART =============== */}
          <StockChart ticker={ticker} stockName={overview.name} />

          {/* =============== FINANCIAL STATEMENTS =============== */}
          <div className="glass-card" style={{ overflow: "hidden" }}>
            <div className="fin-tab-bar">
              <div className="fin-tabs">
                {[
                  { id: "income_statement", label: "Income Statement" },
                  { id: "balance_sheet", label: "Balance Sheet" },
                  { id: "cash_flow", label: "Cash Flow" },
                ].map((tab) => (
                  <button key={tab.id} onClick={() => setActiveFinTab(tab.id)}
                    style={{
                      padding: "8px 16px", borderRadius: "8px", fontSize: "12px", fontWeight: 600,
                      border: "none", cursor: "pointer",
                      background: activeFinTab === tab.id ? "rgba(99,102,241,0.15)" : "transparent",
                      color: activeFinTab === tab.id ? "var(--color-accent-secondary)" : "var(--color-text-muted)",
                      transition: "all 0.2s",
                    }}
                  >{tab.label}</button>
                ))}
              </div>
              <div style={{ display: "flex", gap: "4px" }}>
                {["annual", "quarterly"].map((p) => (
                  <button key={p} onClick={() => setFinPeriod(p)}
                    style={{
                      padding: "6px 14px", borderRadius: "6px", fontSize: "11px", fontWeight: 600,
                      border: "1px solid var(--border-subtle)", cursor: "pointer",
                      background: finPeriod === p ? "rgba(99,102,241,0.12)" : "transparent",
                      color: finPeriod === p ? "var(--color-accent-secondary)" : "var(--color-text-muted)",
                      textTransform: "capitalize",
                    }}
                  >{p}</button>
                ))}
              </div>
            </div>
            <div style={{ padding: "4px" }}>
              <FinancialTable data={financials?.[activeFinTab]} title={activeFinTab} />
            </div>
          </div>

          {/* =============== PEER COMPARISON =============== */}
          {peers && peers.peers?.length > 0 && (
            <div className="glass-card" style={{ overflow: "hidden" }}>
              <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border-subtle)" }}>
                <h3 style={{ fontSize: "13px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--color-text-muted)" }}>
                  Peer Comparison — {peers.sector}
                </h3>
              </div>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                      {["Company", "Price", "Mkt Cap", "P/E", "P/B", "ROE", "Margin", "D/E", "Div%"].map((h) => (
                        <th key={h} style={{ padding: "12px 14px", textAlign: h === "Company" ? "left" : "right", fontWeight: 600, color: "var(--color-text-muted)", fontSize: "10px", textTransform: "uppercase", letterSpacing: "0.05em" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {peers.peers.map((p, i) => (
                      <tr key={p.ticker}
                        style={{
                          borderBottom: "1px solid var(--border-subtle)",
                          background: p.is_target ? "rgba(99,102,241,0.06)" : i % 2 === 0 ? "transparent" : "rgba(99,102,241,0.02)",
                          cursor: "pointer",
                        }}
                        onClick={() => { if (!p.is_target) { setTicker(p.ticker); setSearchQuery(p.ticker); } }}
                        onMouseEnter={(e) => { if (!p.is_target) e.currentTarget.style.background = "rgba(99,102,241,0.08)"; }}
                        onMouseLeave={(e) => { e.currentTarget.style.background = p.is_target ? "rgba(99,102,241,0.06)" : "transparent"; }}
                      >
                        <td style={{ padding: "12px 14px" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                            {p.is_target && <span style={{ width: "3px", height: "16px", borderRadius: "2px", background: "var(--color-accent-primary)" }} />}
                            <div>
                              <span style={{ fontWeight: p.is_target ? 700 : 600, color: "var(--color-text-primary)" }}>{p.ticker}</span>
                              <div style={{ fontSize: "10px", color: "var(--color-text-muted)", marginTop: "1px" }}>{p.name?.slice(0, 25)}</div>
                            </div>
                          </div>
                        </td>
                        <td style={{ padding: "12px 14px", textAlign: "right", fontWeight: 600, fontVariantNumeric: "tabular-nums", color: "var(--color-text-primary)" }}>₹{p.current_price?.toLocaleString("en-IN")}</td>
                        <td style={{ padding: "12px 14px", textAlign: "right", color: "var(--color-text-secondary)", fontVariantNumeric: "tabular-nums" }}>{p.market_cap}</td>
                        <td style={{ padding: "12px 14px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: "var(--color-text-primary)" }}>{p.pe_ratio ?? "—"}</td>
                        <td style={{ padding: "12px 14px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: "var(--color-text-primary)" }}>{p.pb_ratio ?? "—"}</td>
                        <td style={{ padding: "12px 14px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: p.roe > 15 ? "var(--color-accent-green)" : "var(--color-text-primary)" }}>{p.roe != null ? `${p.roe}%` : "—"}</td>
                        <td style={{ padding: "12px 14px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: "var(--color-text-primary)" }}>{p.profit_margin != null ? `${p.profit_margin}%` : "—"}</td>
                        <td style={{ padding: "12px 14px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: p.debt_to_equity > 100 ? "var(--color-accent-red)" : "var(--color-text-primary)" }}>{p.debt_to_equity ?? "—"}</td>
                        <td style={{ padding: "12px 14px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: "var(--color-text-primary)" }}>{p.dividend_yield != null ? `${p.dividend_yield}%` : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* =============== SHAREHOLDING =============== */}
          {shareholding && (shareholding.major_holders?.length > 0 || shareholding.top_institutions?.length > 0) && (
            <div className="responsive-grid-2">
              {/* Major Holders */}
              {shareholding.major_holders?.length > 0 && (
                <div className="glass-card" style={{ padding: "20px" }}>
                  <h3 style={{ fontSize: "13px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--color-text-muted)", marginBottom: "14px" }}>Shareholding Pattern</h3>
                  <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                    {shareholding.major_holders.map((h, i) => {
                      const pct = parseFloat(h.value);
                      return (
                        <div key={i}>
                          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", marginBottom: "4px" }}>
                            <span style={{ color: "var(--color-text-secondary)" }}>{h.label}</span>
                            <span style={{ fontWeight: 700, color: "var(--color-text-primary)" }}>{h.value}</span>
                          </div>
                          {!isNaN(pct) && (
                            <div style={{ height: "5px", borderRadius: "3px", background: "rgba(148,163,184,0.1)", overflow: "hidden" }}>
                              <div style={{ height: "100%", width: `${Math.min(pct, 100)}%`, borderRadius: "3px", background: `hsl(${240 - i * 30}, 70%, 60%)`, transition: "width 0.8s ease" }} />
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Top Institutions */}
              {shareholding.top_institutions?.length > 0 && (
                <div className="glass-card" style={{ padding: "20px" }}>
                  <h3 style={{ fontSize: "13px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--color-text-muted)", marginBottom: "14px" }}>Top Institutional Holders</h3>
                  <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                    {shareholding.top_institutions.map((inst, i) => (
                      <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: "1px solid var(--border-subtle)", fontSize: "12px" }}>
                        <span style={{ color: "var(--color-text-secondary)", flex: 1 }}>{inst.holder}</span>
                        <span style={{ fontWeight: 600, color: "var(--color-text-primary)", fontVariantNumeric: "tabular-nums", marginLeft: "12px" }}>
                          {inst.pct_out ? `${inst.pct_out}%` : `${(inst.shares / 1e7).toFixed(1)}Cr shares`}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Deep Dive CTA */}
          <div className="glass-card" style={{ padding: "24px", textAlign: "center", background: "linear-gradient(135deg, rgba(99,102,241,0.06), rgba(6,182,212,0.04))" }}>
            <p style={{ fontSize: "14px", color: "var(--color-text-muted)", marginBottom: "12px" }}>
              Want AI-powered analysis with moat rating, catalysts & smart verdict?
            </p>
            <button
              onClick={() => onNavigate?.("analysis", ticker)}
              style={{
                padding: "12px 28px", borderRadius: "12px", fontSize: "14px", fontWeight: 700,
                border: "none", cursor: "pointer",
                background: "linear-gradient(135deg, var(--color-accent-primary), var(--color-accent-cyan))", color: "white",
              }}
            >
              🧠 Run AI Deep Dive
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
