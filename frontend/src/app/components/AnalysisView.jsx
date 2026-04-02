"use client";

import { useState, useEffect, useRef } from "react";
import StockChart from "./StockChart";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

// --- Radial Score Ring ---
function ScoreRing({ value, size = 80, color, label }) {
  const r = (size - 12) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (value / 100) * circ;
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "4px" }}>
      <div style={{ position: "relative", width: size, height: size }}>
        <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
          <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="rgba(148,163,184,0.1)" strokeWidth="6" />
          <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth="6"
            strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
            style={{ transition: "stroke-dashoffset 1s ease-out" }} />
        </svg>
        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: size * 0.25, fontWeight: 800, color: "var(--color-text-primary)" }}>
          {value}
        </div>
      </div>
      {label && <span style={{ fontSize: "10px", color: "var(--color-text-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.5px", textAlign: "center" }}>{label}</span>}
    </div>
  );
}

const MOAT_ICONS = { WIDE: "🏰", NARROW: "🛡️", NONE: "⚠️" };
const MOAT_COLORS = { WIDE: "#10b981", NARROW: "#f59e0b", NONE: "#ef4444" };
const ACTION_COLORS = { BUY: "#10b981", HOLD: "#f59e0b", SELL: "#ef4444" };
const IMPACT_COLORS = { POSITIVE: "#10b981", NEGATIVE: "#ef4444", NEUTRAL: "#64748b" };

export default function AnalysisView({ initialTicker }) {
  const [ticker, setTicker] = useState(initialTicker || "");
  const [searchQuery, setSearchQuery] = useState(initialTicker || "");
  const [searchResults, setSearchResults] = useState([]);
  const [stockMeta, setStockMeta] = useState(null);
  const [showDropdown, setShowDropdown] = useState(false);

  // Deep dive state
  const [deepDive, setDeepDive] = useState(null);
  const [ddLoading, setDdLoading] = useState(false);
  const [ddSteps, setDdSteps] = useState([]);
  const terminalRef = useRef(null);

  useEffect(() => {
    if (terminalRef.current) terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
  }, [ddSteps]);

  // Auto-trigger deep dive when ticker changes
  useEffect(() => {
    if (ticker) {
      runDeepDive(ticker);
    }
  }, [ticker]);

  const handleSearch = async (q) => {
    setSearchQuery(q);
    if (q.length < 2) { setSearchResults([]); setShowDropdown(false); return; }
    try {
      const res = await fetch(`${API_BASE}/api/stocks/search?q=${q}&limit=8`);
      const data = await res.json();
      setSearchResults(data);
      setShowDropdown(true);
    } catch (e) { setSearchResults([]); }
  };

  const selectStock = (stock) => {
    setTicker(stock.ticker);
    setSearchQuery(stock.ticker);
    setStockMeta(stock);
    setShowDropdown(false);
    setSearchResults([]);
  };

  // --- Deep Dive ---
  const runDeepDive = async (t) => {
    setDdLoading(true);
    setDeepDive(null);
    setDdSteps([]);

    try {
      const response = await fetch(`${API_BASE}/api/analysis/deep-dive`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker: t }),
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let done = false;
      while (!done) {
        const { value, done: readerDone } = await reader.read();
        if (value) {
          const chunk = decoder.decode(value);
          const lines = chunk.split("\n");
          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const dataStr = line.slice(6).trim();
              if (dataStr === "[DONE]") { setDdLoading(false); break; }
              if (dataStr) {
                try {
                  const data = JSON.parse(dataStr);
                  if (data.type === "step") setDdSteps(prev => [...prev, data.message]);
                  else if (data.type === "result") { setDeepDive(data); setDdLoading(false); }
                } catch (e) {}
              }
            }
          }
        }
        done = readerDone;
      }
    } catch (err) { setDdLoading(false); }
  };

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: "24px" }}>
        <h2 style={{ fontSize: "24px", fontWeight: 700, color: "var(--color-text-primary)" }}>Deep Dive Analysis</h2>
        <p style={{ fontSize: "13px", color: "var(--color-text-muted)", marginTop: "4px" }}>
          Comprehensive AI-powered research on any NSE-listed stock
        </p>
      </div>

      {/* Stock Selector */}
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

      {/* Content */}
      {!ticker ? (
        <div className="glass-card" style={{ padding: "80px 24px", textAlign: "center", background: "linear-gradient(135deg, rgba(99,102,241,0.05), rgba(6,182,212,0.03))" }}>
          <span style={{ fontSize: "56px", display: "block", marginBottom: "16px" }}>🔬</span>
          <p style={{ fontSize: "18px", fontWeight: 700, color: "var(--color-text-primary)" }}>Search for a stock to begin</p>
          <p style={{ fontSize: "14px", color: "var(--color-text-muted)", marginTop: "8px", maxWidth: "400px", margin: "8px auto 0" }}>
            Get competitive moat analysis, financial health scores, catalyst radar, smart verdicts, and better alternatives
          </p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>

          {/* Hero Header */}
          {stockMeta && (
            <div className="glass-card animate-fade-in" style={{ padding: "20px 24px", display: "flex", alignItems: "center", gap: "16px", background: "linear-gradient(135deg, rgba(99,102,241,0.06), rgba(6,182,212,0.04))" }}>
              <div style={{ width: "52px", height: "52px", borderRadius: "14px", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: "20px", color: "white", background: "linear-gradient(135deg, var(--color-accent-primary), var(--color-accent-cyan))", flexShrink: 0 }}>
                {ticker.charAt(0)}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                  <span style={{ fontSize: "20px", fontWeight: 800, color: "var(--color-text-primary)" }}>{ticker}</span>
                  <span style={{ padding: "3px 10px", borderRadius: "6px", fontSize: "11px", fontWeight: 600, background: "rgba(99,102,241,0.12)", color: "var(--color-accent-secondary)" }}>{stockMeta.sector}</span>
                </div>
                <p style={{ fontSize: "14px", color: "var(--color-text-muted)", marginTop: "2px" }}>{stockMeta.name}</p>
              </div>
              {stockMeta.current_price > 0 && (
                <div style={{ textAlign: "right" }}>
                  <p style={{ fontSize: "24px", fontWeight: 800, fontVariantNumeric: "tabular-nums", color: "var(--color-text-primary)" }}>
                    ₹{stockMeta.current_price.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </p>
                  <p style={{ fontSize: "14px", fontWeight: 700, fontVariantNumeric: "tabular-nums", color: stockMeta.change_percent >= 0 ? "var(--color-accent-green)" : "var(--color-accent-red)" }}>
                    {stockMeta.change_percent >= 0 ? "▲ +" : "▼ "}{stockMeta.change_percent.toFixed(2)}%
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Terminal (during loading) */}
          {ddLoading && (
            <div style={{ background: "#0c0a13", border: "1px solid #2a2542", borderRadius: "14px", padding: "16px", fontFamily: "'JetBrains Mono', monospace", fontSize: "13px", color: "#a599e9" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "12px", paddingBottom: "10px", borderBottom: "1px solid #2a2542" }}>
                <div style={{ display: "flex", gap: "6px" }}>
                  <div style={{ width: "10px", height: "10px", borderRadius: "50%", background: "#ef4444" }} />
                  <div style={{ width: "10px", height: "10px", borderRadius: "50%", background: "#f59e0b" }} />
                  <div style={{ width: "10px", height: "10px", borderRadius: "50%", background: "#10b981" }} />
                </div>
                <span style={{ fontSize: "11px", color: "#6b61a3", textTransform: "uppercase", letterSpacing: "1px" }}>Deep Dive Engine</span>
              </div>
              <div ref={terminalRef} style={{ display: "flex", flexDirection: "column", gap: "6px", maxHeight: "200px", overflowY: "auto" }}>
                {ddSteps.map((step, idx) => (
                  <div key={idx}><span style={{ color: "#34d399", marginRight: "10px" }}>&gt;</span>{step}</div>
                ))}
                <div style={{ color: "var(--color-text-muted)", animation: "pulse 1.5s infinite" }}>
                  <span style={{ color: "#34d399", marginRight: "10px" }}>&gt;</span> _
                </div>
              </div>
            </div>
          )}

          {/* Deep Dive Results */}
          {deepDive && (
            <>
              {/* Row 1: Moat + Financial Health */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px" }}>
                {/* Competitive Moat */}
                <div className="glass-card animate-fade-in" style={{ padding: "24px" }}>
                  <h4 style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "1px", color: "var(--color-text-muted)", marginBottom: "16px" }}>Competitive Moat</h4>
                  <div style={{ display: "flex", alignItems: "center", gap: "16px", marginBottom: "16px" }}>
                    <div style={{ width: "56px", height: "56px", borderRadius: "14px", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "28px", background: `${MOAT_COLORS[deepDive.moat_rating]}15`, border: `2px solid ${MOAT_COLORS[deepDive.moat_rating]}30` }}>
                      {MOAT_ICONS[deepDive.moat_rating]}
                    </div>
                    <div>
                      <span style={{ fontSize: "22px", fontWeight: 800, color: MOAT_COLORS[deepDive.moat_rating] }}>{deepDive.moat_rating}</span>
                      <span style={{ fontSize: "14px", color: "var(--color-text-muted)", marginLeft: "8px" }}>Moat</span>
                    </div>
                  </div>
                  <p style={{ fontSize: "14px", color: "var(--color-text-secondary)", lineHeight: 1.6 }}>{deepDive.moat_reason}</p>
                </div>

                {/* Financial Health */}
                <div className="glass-card animate-fade-in" style={{ padding: "24px" }}>
                  <h4 style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "1px", color: "var(--color-text-muted)", marginBottom: "16px" }}>Financial Health</h4>
                  {deepDive.financials && (
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
                      {[
                        { label: "Revenue Growth", value: deepDive.financials.revenue_growth, score: deepDive.financials.revenue_growth_score },
                        { label: "Profit Margin", value: deepDive.financials.profit_margin, score: deepDive.financials.margin_score },
                        { label: "Debt/Equity", value: deepDive.financials.debt_to_equity, score: deepDive.financials.debt_score },
                        { label: "ROE", value: deepDive.financials.roe, score: deepDive.financials.roe_score },
                      ].map(m => (
                        <div key={m.label}>
                          <ScoreRing value={m.score || 50} size={70} color={m.score > 70 ? "#10b981" : m.score > 40 ? "#f59e0b" : "#ef4444"} label={m.label} />
                          <div style={{ textAlign: "center", marginTop: "4px", fontSize: "14px", fontWeight: 700, color: "var(--color-text-primary)" }}>{m.value}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Row 2: Catalyst Timeline + Smart Verdict */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px" }}>
                {/* Catalyst Radar */}
                <div className="glass-card animate-fade-in" style={{ padding: "24px" }}>
                  <h4 style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "1px", color: "var(--color-text-muted)", marginBottom: "16px", display: "flex", alignItems: "center", gap: "6px" }}>
                    📡 Catalyst Radar
                  </h4>
                  <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
                    {deepDive.catalysts?.map((cat, i) => (
                      <div key={i} style={{ display: "flex", gap: "14px", alignItems: "flex-start" }}>
                        <div style={{ width: "10px", height: "10px", borderRadius: "50%", marginTop: "6px", flexShrink: 0, background: IMPACT_COLORS[cat.impact] || "#64748b" }} />
                        <div style={{ flex: 1 }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <span style={{ fontSize: "14px", fontWeight: 600, color: "var(--color-text-primary)" }}>{cat.title}</span>
                            <span style={{ fontSize: "11px", padding: "2px 8px", borderRadius: "4px", background: "var(--color-bg-card-hover)", color: "var(--color-text-muted)" }}>{cat.timeline}</span>
                          </div>
                          <p style={{ fontSize: "13px", color: "var(--color-text-secondary)", marginTop: "4px", lineHeight: 1.5 }}>{cat.description}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Smart Verdict */}
                <div className="glass-card animate-fade-in" style={{ padding: "24px", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
                  <div>
                    <h4 style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "1px", color: "var(--color-text-muted)", marginBottom: "16px", display: "flex", alignItems: "center", gap: "6px" }}>
                      🎯 Smart Verdict
                    </h4>
                    {deepDive.verdict && (
                      <>
                        <div style={{ display: "flex", alignItems: "center", gap: "16px", marginBottom: "16px" }}>
                          <div style={{ padding: "10px 24px", borderRadius: "12px", fontSize: "20px", fontWeight: 800, background: `${ACTION_COLORS[deepDive.verdict.action]}20`, color: ACTION_COLORS[deepDive.verdict.action], border: `2px solid ${ACTION_COLORS[deepDive.verdict.action]}40` }}>
                            {deepDive.verdict.action}
                          </div>
                          <div>
                            <div style={{ fontSize: "13px", color: "var(--color-text-muted)" }}>Confidence</div>
                            <div style={{ fontSize: "22px", fontWeight: 800, color: "var(--color-text-primary)" }}>{deepDive.verdict.confidence}%</div>
                          </div>
                        </div>
                        <p style={{ fontSize: "14px", color: "var(--color-text-secondary)", lineHeight: 1.6, marginBottom: "16px" }}>{deepDive.verdict.thesis}</p>
                        <div style={{ padding: "12px 16px", background: "rgba(99,102,241,0.06)", borderRadius: "10px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <span style={{ fontSize: "12px", color: "var(--color-text-muted)", fontWeight: 600 }}>Target Range</span>
                          <span style={{ fontSize: "16px", fontWeight: 700, color: "var(--color-text-primary)", fontVariantNumeric: "tabular-nums" }}>
                            ₹{deepDive.verdict.target_low?.toLocaleString("en-IN")} — ₹{deepDive.verdict.target_high?.toLocaleString("en-IN")}
                          </span>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              </div>

              {/* Row 3: Better Alternatives */}
              {deepDive.alternatives?.length > 0 && (
                <div className="glass-card animate-fade-in" style={{ padding: "24px" }}>
                  <h4 style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "1px", color: "var(--color-accent-cyan)", marginBottom: "16px", display: "flex", alignItems: "center", gap: "6px" }}>
                    🔄 Consider These Alternatives
                  </h4>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
                    {deepDive.alternatives.map((alt, i) => (
                      <div key={i} style={{ padding: "16px", background: "rgba(6,182,212,0.05)", border: "1px solid rgba(6,182,212,0.15)", borderRadius: "12px", cursor: "pointer", transition: "all 0.2s" }}
                        onClick={() => { setTicker(alt.ticker); setSearchQuery(alt.ticker); setStockMeta(null); }}
                        onMouseEnter={e => e.currentTarget.style.borderColor = "rgba(6,182,212,0.4)"}
                        onMouseLeave={e => e.currentTarget.style.borderColor = "rgba(6,182,212,0.15)"}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                          <span style={{ fontSize: "16px", fontWeight: 700, color: "var(--color-text-primary)" }}>{alt.ticker}</span>
                          <span style={{ fontSize: "11px", padding: "3px 8px", borderRadius: "6px", background: "rgba(6,182,212,0.12)", color: "var(--color-accent-cyan)", fontWeight: 600 }}>Alternative</span>
                        </div>
                        <p style={{ fontSize: "13px", color: "var(--color-text-secondary)", marginBottom: "6px" }}>{alt.name}</p>
                        <p style={{ fontSize: "13px", color: "var(--color-text-muted)", lineHeight: 1.5 }}>{alt.why}</p>
                        <div style={{ marginTop: "8px", padding: "6px 10px", background: "rgba(16,185,129,0.08)", borderRadius: "6px", fontSize: "12px", color: "#10b981", fontWeight: 600 }}>
                          Edge: {alt.edge}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Price Chart */}
              <StockChart ticker={ticker} stockName={deepDive?.company || ticker} />

              {/* Re-analyze button */}
              <button onClick={() => runDeepDive(ticker)}
                style={{ alignSelf: "flex-end", padding: "8px 16px", borderRadius: "8px", fontSize: "12px", fontWeight: 500, border: "1px solid var(--border-subtle)", background: "transparent", color: "var(--color-text-muted)", cursor: "pointer" }}>
                ↻ Re-analyze
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
