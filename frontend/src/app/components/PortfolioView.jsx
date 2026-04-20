"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import { supabase } from "../lib/supabase";
import { API_BASE as _SHARED_API_BASE } from "../lib/api";
import { claimText, claimSource } from "../lib/claim";
const API_BASE = _SHARED_API_BASE;

const COLORS = [
  "#6366f1", "#06b6d4", "#10b981", "#f59e0b", "#ef4444",
  "#8b5cf6", "#ec4899", "#14b8a6", "#f97316", "#3b82f6",
];

const SIGNAL_STYLES = {
  BUY:    { bg: "rgba(16,185,129,0.15)", color: "#10b981", label: "BUY" },
  HOLD:   { bg: "rgba(245,158,11,0.15)", color: "#f59e0b", label: "HOLD" },
  REDUCE: { bg: "rgba(239,68,68,0.15)", color: "#ef4444", label: "REDUCE" },
};

function ScoreGauge({ score, size = 120, label }) {
  const radius = (size - 16) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  const color = score > 70 ? "#10b981" : score > 40 ? "#f59e0b" : "#ef4444";
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "6px" }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <circle cx={size/2} cy={size/2} r={radius} fill="none" stroke="rgba(148,163,184,0.1)" strokeWidth="8" />
        <circle cx={size/2} cy={size/2} r={radius} fill="none" stroke={color} strokeWidth="8"
          strokeDasharray={circumference} strokeDashoffset={offset} strokeLinecap="round"
          style={{ transition: "stroke-dashoffset 1.2s ease-out" }} />
      </svg>
      <div style={{ position: "absolute", marginTop: size * 0.3, textAlign: "center" }}>
        <div style={{ fontSize: size * 0.3, fontWeight: 800, color: "var(--color-text-primary)" }}>{score}</div>
        <div style={{ fontSize: "10px", color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "1px" }}>/100</div>
      </div>
      {label && <span style={{ fontSize: "11px", color: "var(--color-text-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.5px" }}>{label}</span>}
    </div>
  );
}

function MiniBar({ value, color }) {
  return (
    <div style={{ width: "100%", height: "6px", borderRadius: "3px", background: "rgba(148,163,184,0.1)", overflow: "hidden" }}>
      <div style={{ height: "100%", width: `${value}%`, borderRadius: "3px", background: color, transition: "width 1s ease-out" }} />
    </div>
  );
}

export default function PortfolioView({ onNavigate }) {
  const [portfolio, setPortfolio] = useState(null);
  const [loading, setLoading] = useState(true);
  const [uploadingCsv, setUploadingCsv] = useState(false);
  const [intel, setIntel] = useState(null);
  const [intelLoading, setIntelLoading] = useState(false);
  const [intelSteps, setIntelSteps] = useState([]);
  const terminalRef = useRef(null);

  useEffect(() => {
    if (terminalRef.current) terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
  }, [intelSteps]);

  const fetchPortfolio = useCallback(async () => {
    setLoading(true);
    try {
      // 1. Get positions from Supabase
      const { data: rows, error } = await supabase
        .from("portfolio")
        .select("ticker, quantity, buy_price, added_at")
        .order("added_at", { ascending: true });

      if (error) throw error;
      if (!rows || rows.length === 0) { setPortfolio({ holdings_count: 0, positions: [], allocation: [], total_invested: 0, current_value: 0, total_pnl: 0, total_pnl_percent: 0, day_change: 0, day_change_percent: 0 }); return; }

      // 2. Enrich with live P&L from backend
      const res = await fetch(`${API_BASE}/api/portfolio/enrich`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ positions: rows.map((r) => ({ ticker: r.ticker, quantity: r.quantity, buy_price: r.buy_price })) }),
      });

      if (res.ok) {
        setPortfolio(await res.json());
      } else {
        // Backend unavailable — show raw data without enrichment
        setPortfolio({
          holdings_count: rows.length,
          positions: rows.map((r) => ({ ticker: r.ticker, name: r.ticker, sector: "—", quantity: r.quantity, buy_price: r.buy_price, current_price: 0, invested_value: r.quantity * r.buy_price, current_value: 0, pnl: 0, pnl_percent: 0, added_at: r.added_at })),
          allocation: [], total_invested: rows.reduce((s, r) => s + r.quantity * r.buy_price, 0),
          current_value: 0, total_pnl: 0, total_pnl_percent: 0, day_change: 0, day_change_percent: 0,
        });
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchPortfolio(); }, [fetchPortfolio]);

  const handleConnectZerodha = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/zerodha/login`);
      const data = await res.json();
      if (data.url) window.location.href = data.url;
    } catch { alert("Failed to connect to Zerodha"); }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setUploadingCsv(true);
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch(`${API_BASE}/api/zerodha/upload-csv`, { method: "POST", body: formData });
      const data = await res.json();
      if (res.ok && data.positions) {
        // Replace existing holdings with the CSV snapshot (Kite is source of truth)
        await supabase.from("portfolio").delete().neq("ticker", "__never__");
        for (const pos of data.positions) {
          await supabase.from("portfolio").upsert({ ticker: pos.ticker, quantity: pos.quantity, buy_price: pos.buy_price }, { onConflict: "ticker" });
        }
        alert(`Imported ${data.positions.length} positions from Kite`);
        fetchPortfolio();
      } else { alert(data.detail || "Upload failed"); }
    } catch { alert("Network error during upload"); }
    finally { setUploadingCsv(false); e.target.value = null; }
  };

  const runIntelligence = async () => {
    if (!portfolio?.positions?.length) return;
    setIntelLoading(true);
    setIntel(null);
    setIntelSteps([]);
    try {
      const response = await fetch(`${API_BASE}/api/intelligence/portfolio`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ positions: portfolio.positions.map((p) => ({ ticker: p.ticker, quantity: p.quantity, buy_price: p.buy_price })) }),
      });
      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let done = false;
      while (!done) {
        const { value, done: readerDone } = await reader.read();
        if (value) {
          const chunk = decoder.decode(value);
          for (const line of chunk.split("\n")) {
            if (!line.startsWith("data: ")) continue;
            const dataStr = line.slice(6).trim();
            if (dataStr === "[DONE]") { setIntelLoading(false); break; }
            if (dataStr) {
              try {
                const data = JSON.parse(dataStr);
                if (data.type === "step") setIntelSteps((prev) => [...prev, data.message]);
                else if (data.type === "result") { setIntel(data); setIntelLoading(false); }
              } catch {}
            }
          }
        }
        done = readerDone;
      }
    } catch { setIntelLoading(false); }
  };

  const verdictMap = {};
  if (intel?.holdings_verdicts) intel.holdings_verdicts.forEach((v) => { verdictMap[v.ticker] = v; });

  return (
    <div>
      <div className="section-header">
        <div>
          <h2 style={{ fontSize: "24px", fontWeight: 700, color: "var(--color-text-primary)" }}>Smart Portfolio</h2>
          <p style={{ fontSize: "13px", color: "var(--color-text-muted)", marginTop: "4px" }}>AI-powered portfolio intelligence & analysis</p>
        </div>
        <div className="portfolio-header-actions">
          <button onClick={handleConnectZerodha}
            style={{ padding: "10px 16px", borderRadius: "10px", fontSize: "13px", fontWeight: 600, border: "1px solid var(--color-accent-primary)", cursor: "pointer", background: "rgba(99,102,241,0.1)", color: "var(--color-accent-primary)" }}>
            ⚡ Kite Sync
          </button>
          <label style={{ cursor: "pointer", padding: "10px 16px", borderRadius: "10px", fontSize: "13px", fontWeight: 600, border: "1px solid var(--border-subtle)", background: "transparent", color: "var(--color-text-primary)", display: "flex", alignItems: "center", gap: "6px" }}>
            📄 {uploadingCsv ? "Uploading..." : "Kite CSV"}
            <input type="file" accept=".csv" onChange={handleFileUpload} style={{ display: "none" }} disabled={uploadingCsv} />
          </label>
        </div>
      </div>

      {loading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          {[1, 2, 3].map((i) => <div key={i} className="shimmer" style={{ height: "100px", borderRadius: "16px" }} />)}
        </div>
      ) : !portfolio || portfolio.holdings_count === 0 ? (
        <div className="glass-card" style={{ padding: "60px 24px", textAlign: "center" }}>
          <span style={{ fontSize: "64px", display: "block", marginBottom: "16px" }}>💼</span>
          <p style={{ fontSize: "18px", fontWeight: 700, color: "var(--color-text-primary)" }}>Import Your Portfolio</p>
          <p style={{ fontSize: "14px", color: "var(--color-text-muted)", marginTop: "8px", maxWidth: "400px", margin: "8px auto 0" }}>
            Connect your Zerodha account or upload a CSV to get AI-powered analysis, recommendations, and risk alerts
          </p>
        </div>
      ) : (
        <>
          <div className="responsive-grid-4" style={{ marginBottom: "24px" }}>
            {[
              { label: "Total Invested", value: `₹${portfolio.total_invested.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`, color: "var(--color-text-primary)" },
              { label: "Current Value", value: `₹${portfolio.current_value.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`, color: "var(--color-accent-secondary)" },
              { label: "Total P&L", value: `${portfolio.total_pnl >= 0 ? "+" : ""}₹${portfolio.total_pnl.toLocaleString("en-IN", { minimumFractionDigits: 2 })} (${portfolio.total_pnl_percent >= 0 ? "+" : ""}${portfolio.total_pnl_percent}%)`, color: portfolio.total_pnl >= 0 ? "var(--color-accent-green)" : "var(--color-accent-red)" },
              { label: "Day Change", value: `${portfolio.day_change >= 0 ? "+" : ""}₹${portfolio.day_change.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`, color: portfolio.day_change >= 0 ? "var(--color-accent-green)" : "var(--color-accent-red)" },
            ].map((card) => (
              <div key={card.label} className="glass-card" style={{ padding: "18px" }}>
                <p style={{ fontSize: "10px", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--color-text-muted)" }}>{card.label}</p>
                <p style={{ fontSize: "18px", fontWeight: 700, marginTop: "6px", fontVariantNumeric: "tabular-nums", color: card.color }}>{card.value}</p>
              </div>
            ))}
          </div>

          {!intel && !intelLoading && (
            <div className="glass-card animate-fade-in" style={{ padding: "28px", marginBottom: "24px", textAlign: "center", background: "linear-gradient(135deg, rgba(99,102,241,0.08), rgba(6,182,212,0.06))", border: "1px solid rgba(99,102,241,0.2)" }}>
              <span style={{ fontSize: "36px", display: "block", marginBottom: "12px" }}>🧠</span>
              <h3 style={{ fontSize: "18px", fontWeight: 700, color: "var(--color-text-primary)", marginBottom: "8px" }}>Analyze My Portfolio</h3>
              <p style={{ fontSize: "13px", color: "var(--color-text-muted)", maxWidth: "500px", margin: "0 auto 20px" }}>
                Get AI-powered insights: portfolio health score, per-stock signals, risk alerts, and stock recommendations
              </p>
              <button onClick={runIntelligence}
                style={{ padding: "12px 32px", borderRadius: "12px", fontSize: "14px", fontWeight: 700, border: "none", cursor: "pointer", background: "linear-gradient(135deg, var(--color-accent-primary), var(--color-accent-cyan))", color: "white" }}>
                🚀 Run AI Analysis
              </button>
            </div>
          )}

          {intelLoading && (
            <div className="glass-card" style={{ marginBottom: "24px", overflow: "hidden" }}>
              <div style={{ background: "#0c0a13", padding: "16px", fontFamily: "'JetBrains Mono', monospace", fontSize: "13px", color: "#a599e9", borderRadius: "16px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "12px", paddingBottom: "10px", borderBottom: "1px solid #2a2542" }}>
                  <div style={{ display: "flex", gap: "6px" }}>
                    {["#ef4444","#f59e0b","#10b981"].map((c) => <div key={c} style={{ width: "10px", height: "10px", borderRadius: "50%", background: c }} />)}
                  </div>
                  <span style={{ fontSize: "11px", color: "#6b61a3", textTransform: "uppercase", letterSpacing: "1px" }}>Portfolio Intelligence Engine</span>
                </div>
                <div ref={terminalRef} style={{ display: "flex", flexDirection: "column", gap: "6px", maxHeight: "160px", overflowY: "auto" }}>
                  {intelSteps.map((step, idx) => (
                    <div key={idx}><span style={{ color: "#34d399", marginRight: "10px" }}>&gt;</span>{step}</div>
                  ))}
                  <div><span style={{ color: "#34d399", marginRight: "10px" }}>&gt;</span> _</div>
                </div>
              </div>
            </div>
          )}

          {intel && (
            <div style={{ marginBottom: "24px", display: "flex", flexDirection: "column", gap: "20px" }}>
              <div className="responsive-grid-intel">
                <div className="glass-card" style={{ padding: "24px", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", position: "relative" }}>
                  <ScoreGauge score={intel.portfolio_health_score} size={130} label="Portfolio Health" />
                </div>
                <div className="glass-card" style={{ padding: "24px", display: "flex", flexDirection: "column", gap: "16px", justifyContent: "center" }}>
                  <h4 style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "1px", color: "var(--color-text-muted)", marginBottom: "4px" }}>Health Breakdown</h4>
                  {intel.health_breakdown && Object.entries(intel.health_breakdown).map(([key, val]) => (
                    <div key={key}>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", marginBottom: "4px" }}>
                        <span style={{ color: "var(--color-text-secondary)", textTransform: "capitalize" }}>{key}</span>
                        <span style={{ color: "var(--color-text-primary)", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{val}/100</span>
                      </div>
                      <MiniBar value={val} color={val > 70 ? "#10b981" : val > 40 ? "#f59e0b" : "#ef4444"} />
                    </div>
                  ))}
                </div>
                <div className="glass-card" style={{ padding: "24px" }}>
                  <h4 style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "1px", color: "var(--color-accent-red)", marginBottom: "16px" }}>⚠️ Top Risks</h4>
                  <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                    {intel.top_risks?.map((risk, i) => (
                      <div key={i} style={{ padding: "10px 12px", background: "rgba(239,68,68,0.06)", borderRadius: "10px", borderLeft: "3px solid var(--color-accent-red)" }}>
                        <p style={{ fontSize: "13px", fontWeight: 600, color: "var(--color-text-primary)" }}>{risk.title}</p>
                        <p title={claimSource(risk.description) || ""} style={{ fontSize: "12px", color: "var(--color-text-muted)", marginTop: "3px" }}>{claimText(risk.description)}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {(intel.suggested_directions?.length > 0 || intel.recommendations?.length > 0) && (
                <div className="glass-card" style={{ padding: "24px" }}>
                  <h4 style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "1px", color: "var(--color-accent-cyan)", marginBottom: "16px" }}>💡 Suggested Directions</h4>
                  <div className="responsive-grid-3">
                    {(intel.suggested_directions || intel.recommendations || []).map((rec, i) => {
                      const focus = rec.focus || rec.ticker || rec.name || "Direction";
                      const conviction = rec.conviction || "MEDIUM";
                      const rationale = rec.rationale;
                      return (
                        <div key={i} style={{ padding: "16px", background: "rgba(6,182,212,0.05)", border: "1px solid rgba(6,182,212,0.15)", borderRadius: "12px", transition: "all 0.2s" }}
                          onMouseEnter={(e) => { e.currentTarget.style.borderColor = "rgba(6,182,212,0.4)"; }}
                          onMouseLeave={(e) => { e.currentTarget.style.borderColor = "rgba(6,182,212,0.15)"; }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px", gap: "8px" }}>
                            <span style={{ fontSize: "14px", fontWeight: 700, color: "var(--color-text-primary)" }}>{focus}</span>
                            <span style={{ padding: "3px 8px", borderRadius: "6px", fontSize: "10px", fontWeight: 700, background: conviction === "HIGH" ? "rgba(16,185,129,0.15)" : "rgba(245,158,11,0.15)", color: conviction === "HIGH" ? "#10b981" : "#f59e0b", flexShrink: 0 }}>
                              {conviction}
                            </span>
                          </div>
                          <p title={claimSource(rationale) || ""} style={{ fontSize: "13px", color: "var(--color-text-secondary)", lineHeight: 1.5 }}>{claimText(rationale)}</p>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              <button onClick={() => { setIntel(null); setIntelSteps([]); }}
                style={{ alignSelf: "flex-end", padding: "8px 16px", borderRadius: "8px", fontSize: "12px", fontWeight: 500, border: "1px solid var(--border-subtle)", background: "transparent", color: "var(--color-text-muted)", cursor: "pointer" }}>
                ↻ Re-analyze
              </button>
            </div>
          )}

          <div className="responsive-grid-holdings">
            <div className="glass-card" style={{ overflow: "hidden" }}>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                      {["Stock", "Qty", "Buy", "LTP", "P&L", "Signal"].map((h) => (
                        <th key={h} style={{ padding: "14px 12px", textAlign: "left", fontWeight: 600, color: "var(--color-text-muted)", textTransform: "uppercase", fontSize: "10px", letterSpacing: "0.05em" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {portfolio.positions.map((pos) => {
                      const isPos = pos.pnl >= 0;
                      const verdict = verdictMap[pos.ticker];
                      const sig = verdict ? SIGNAL_STYLES[verdict.signal] : null;
                      return (
                        <tr key={pos.ticker} style={{ borderBottom: "1px solid var(--border-subtle)", cursor: "pointer" }}
                          onClick={() => onNavigate?.("analysis", pos.ticker)}
                          onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(99,102,241,0.05)"; }}
                          onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}>
                          <td style={{ padding: "14px 12px" }}>
                            <div style={{ fontWeight: 600, color: "var(--color-text-primary)" }}>{pos.ticker}</div>
                            <div style={{ fontSize: "11px", color: "var(--color-text-muted)", marginTop: "2px" }}>{pos.name}</div>
                          </td>
                          <td style={{ padding: "14px 12px", fontVariantNumeric: "tabular-nums", color: "var(--color-text-secondary)" }}>{pos.quantity}</td>
                          <td style={{ padding: "14px 12px", fontVariantNumeric: "tabular-nums", color: "var(--color-text-secondary)" }}>₹{pos.buy_price.toFixed(2)}</td>
                          <td style={{ padding: "14px 12px", fontWeight: 600, fontVariantNumeric: "tabular-nums", color: "var(--color-text-primary)" }}>₹{pos.current_price.toFixed(2)}</td>
                          <td style={{ padding: "14px 12px", fontWeight: 600, fontVariantNumeric: "tabular-nums", color: isPos ? "var(--color-accent-green)" : "var(--color-accent-red)" }}>
                            {isPos ? "+" : ""}₹{pos.pnl.toFixed(2)}
                            <div style={{ fontSize: "11px" }}>({isPos ? "+" : ""}{pos.pnl_percent.toFixed(2)}%)</div>
                          </td>
                          <td style={{ padding: "14px 12px" }}>
                            {sig ? (
                              <div title={claimText(verdict.reason)} style={{ display: "inline-flex", alignItems: "center", gap: "4px", padding: "4px 10px", borderRadius: "6px", fontSize: "11px", fontWeight: 700, background: sig.bg, color: sig.color }}>
                                {sig.label}
                              </div>
                            ) : <span style={{ fontSize: "11px", color: "var(--color-text-muted)" }}>—</span>}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="glass-card" style={{ padding: "20px" }}>
              <h3 style={{ fontSize: "13px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--color-text-muted)", marginBottom: "16px" }}>Sector Allocation</h3>
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie data={portfolio.allocation} dataKey="value" nameKey="sector" cx="50%" cy="50%" outerRadius={80} innerRadius={45} paddingAngle={2}>
                    {portfolio.allocation.map((_, idx) => <Cell key={idx} fill={COLORS[idx % COLORS.length]} />)}
                  </Pie>
                  <Tooltip contentStyle={{ background: "var(--color-bg-card)", border: "1px solid var(--border-subtle)", borderRadius: "8px", fontSize: "12px", color: "var(--color-text-primary)" }}
                    formatter={(val, name) => [`₹${val.toLocaleString("en-IN")}`, name]} />
                </PieChart>
              </ResponsiveContainer>
              <div style={{ display: "flex", flexDirection: "column", gap: "6px", marginTop: "12px" }}>
                {portfolio.allocation.map((a, i) => (
                  <div key={a.sector} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: "12px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                      <div style={{ width: "8px", height: "8px", borderRadius: "2px", background: COLORS[i % COLORS.length] }} />
                      <span style={{ color: "var(--color-text-secondary)" }}>{a.sector}</span>
                    </div>
                    <span style={{ color: "var(--color-text-muted)", fontVariantNumeric: "tabular-nums" }}>{a.percent}%</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </>
      )}

    </div>
  );
}
