"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import { supabase } from "../lib/supabase";
import { API_BASE as _SHARED_API_BASE } from "../lib/api";
import { claimText, claimSource } from "../lib/claim";
import PortfolioContextCard from "./PortfolioContextCard";
import RiskMetricsCard from "./RiskMetricsCard";
import MissionControlLoader from "./MissionControlLoader";
import { useToast } from "./Toast";
import { LoaderHeader, Skeleton } from "./Loaders";
import { useAuth } from "../context/AuthContext";
import { prewarmIntelligence } from "../lib/prewarm";
import { readSSE } from "../lib/sseStream";
const API_BASE = _SHARED_API_BASE;

const COLORS = [
  "#6366f1", "#06b6d4", "#10b981", "#f59e0b", "#ef4444",
  "#8b5cf6", "#ec4899", "#14b8a6", "#f97316", "#3b82f6",
];

// Compliance: we are unregistered (not SEBI RA), so we surface stance/assessment
// language only — never action verbs like buy/sell/hold. Backend now emits
// BULLISH/NEUTRAL/CAUTIOUS; legacy keys kept for cached/old responses.
const SIGNAL_STYLES = {
  BULLISH:  { bg: "rgba(16,185,129,0.15)", color: "#10b981", label: "BULLISH" },
  NEUTRAL:  { bg: "rgba(245,158,11,0.15)", color: "#f59e0b", label: "NEUTRAL" },
  CAUTIOUS: { bg: "rgba(239,68,68,0.15)", color: "#ef4444", label: "CAUTIOUS" },
  // Legacy aliases — render with soft labels even if backend cache returns old keys.
  BUY:    { bg: "rgba(16,185,129,0.15)", color: "#10b981", label: "BULLISH" },
  HOLD:   { bg: "rgba(245,158,11,0.15)", color: "#f59e0b", label: "NEUTRAL" },
  REDUCE: { bg: "rgba(239,68,68,0.15)", color: "#ef4444", label: "CAUTIOUS" },
  SELL:   { bg: "rgba(239,68,68,0.15)", color: "#ef4444", label: "CAUTIOUS" },
};

export default function PortfolioView({ onNavigate }) {
  const toast = useToast();
  const { user } = useAuth();
  const [portfolio, setPortfolio] = useState(null);
  // Active AI tool tab. Components stay mounted (state preserved) — we toggle
  // visibility via CSS so switching tabs doesn't wipe in-flight results.
  const [aiTab, setAiTab] = useState("context");
  const [loading, setLoading] = useState(true);
  const [uploadingCsv, setUploadingCsv] = useState(false);
  const [intel, setIntel] = useState(null);
  const [intelLoading, setIntelLoading] = useState(false);
  const [intelSteps, setIntelSteps] = useState([]);

  const fetchPortfolio = useCallback(async () => {
    if (!user?.id) return;
    setLoading(true);
    try {
      // 1. Get positions from Supabase — scoped to current user.
      const { data: rows, error } = await supabase
        .from("portfolio")
        .select("ticker, quantity, buy_price, added_at")
        .eq("user_id", user.id)
        .order("added_at", { ascending: true });

      if (error) throw error;
      if (!rows || rows.length === 0) { setPortfolio({ holdings_count: 0, positions: [], allocation: [], total_invested: 0, current_value: 0, total_pnl: 0, total_pnl_percent: 0, day_change: 0, day_change_percent: 0 }); return; }

      // 2. Enrich with live P&L from backend
      const fallback = () => ({
        holdings_count: rows.length,
        positions: rows.map((r) => ({ ticker: r.ticker, name: r.ticker, sector: "—", quantity: r.quantity, buy_price: r.buy_price, current_price: 0, invested_value: r.quantity * r.buy_price, current_value: 0, pnl: 0, pnl_percent: 0, added_at: r.added_at })),
        allocation: [], total_invested: rows.reduce((s, r) => s + r.quantity * r.buy_price, 0),
        current_value: 0, total_pnl: 0, total_pnl_percent: 0, day_change: 0, day_change_percent: 0,
      });

      try {
        const res = await fetch(`${API_BASE}/api/portfolio/enrich`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ positions: rows.map((r) => ({ ticker: r.ticker, quantity: r.quantity, buy_price: r.buy_price })) }),
        });
        if (res.ok) setPortfolio(await res.json());
        else setPortfolio(fallback());
      } catch {
        // Backend unreachable — render raw holdings without enrichment.
        setPortfolio(fallback());
      }
    } finally {
      setLoading(false);
    }
  }, [user?.id]);

  useEffect(() => { fetchPortfolio(); }, [fetchPortfolio]);

  const handleConnectZerodha = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/zerodha/login`);
      const data = await res.json();
      if (data.url) window.location.href = data.url;
    } catch { toast.error("Failed to connect to Zerodha"); }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (!user?.id) {
      toast.error("Please sign in to upload your portfolio.");
      e.target.value = null;
      return;
    }
    setUploadingCsv(true);
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch(`${API_BASE}/api/zerodha/upload-csv`, { method: "POST", body: formData });
      const data = await res.json();
      if (res.ok && data.positions) {
        // Replace the current user's holdings with the CSV snapshot (Kite is source of truth).
        // Scope delete to user_id — never run a global delete.
        await supabase.from("portfolio").delete().eq("user_id", user.id);
        for (const pos of data.positions) {
          await supabase.from("portfolio").upsert(
            { ticker: pos.ticker, quantity: pos.quantity, buy_price: pos.buy_price, user_id: user.id },
            { onConflict: "ticker,user_id" }
          );
        }
        // Warm the backend intelligence cache while the user reads the toast.
        try {
          const { data: watchRows } = await supabase
            .from("watchlist").select("ticker").eq("user_id", user.id);
          prewarmIntelligence({
            positions: data.positions,
            watchlistTickers: (watchRows || []).map((r) => r.ticker),
          });
        } catch { /* prewarm is best-effort */ }
        toast.success(`Imported ${data.positions.length} positions from Kite`);
        fetchPortfolio();
      } else { toast.error(data.detail || "Upload failed"); }
    } catch { toast.error("Network error during upload"); }
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
      // readSSE handles Render's edge fragmenting the result payload across
      // multiple TCP chunks — the old chunk.split("\n") parser silently
      // dropped partial events and the result never arrived.
      for await (const data of readSSE(response)) {
        if (data === "[DONE]") { setIntelLoading(false); break; }
        if (data.type === "step") setIntelSteps((prev) => [...prev, data.message]);
        else if (data.type === "result") { setIntel(data); setIntelLoading(false); }
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
        <div>
          <LoaderHeader label="Computing live P&L…" />
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "16px", marginBottom: "16px" }}>
            {[1, 2, 3, 4].map((i) => (
              <Skeleton key={i} h={70} r={16} />
            ))}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} h={100} r={16} />
            ))}
          </div>
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
          <div className="responsive-grid-4" style={{ marginBottom: "20px" }}>
            {[
              { label: "Total Invested", value: `₹${portfolio.total_invested.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`, color: "var(--color-text-primary)" },
              { label: "Current Value", value: `₹${portfolio.current_value.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`, color: "var(--color-accent-secondary)" },
              { label: "Total P&L", value: `${portfolio.total_pnl >= 0 ? "+" : ""}₹${portfolio.total_pnl.toLocaleString("en-IN", { minimumFractionDigits: 2 })} (${portfolio.total_pnl_percent >= 0 ? "+" : ""}${portfolio.total_pnl_percent}%)`, color: portfolio.total_pnl >= 0 ? "var(--color-accent-green)" : "var(--color-accent-red)" },
              { label: "Day Change", value: `${portfolio.day_change >= 0 ? "+" : ""}₹${portfolio.day_change.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`, color: portfolio.day_change >= 0 ? "var(--color-accent-green)" : "var(--color-accent-red)" },
            ].map((card) => (
              <div key={card.label} className="glass-card" style={{ padding: "16px" }}>
                <p style={{ fontSize: "10px", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--color-text-muted)" }}>{card.label}</p>
                <p style={{ fontSize: "18px", fontWeight: 700, marginTop: "6px", fontVariantNumeric: "tabular-nums", color: card.color }}>{card.value}</p>
              </div>
            ))}
          </div>

          {/* AI TOOLS PANEL — tabbed, replaces three stacked cards.
              Sections stay mounted; only the active one is visible. */}
          <div style={{ marginBottom: "20px" }}>
            <div
              style={{
                display: "flex",
                gap: "6px",
                padding: "4px",
                background: "var(--color-bg-secondary)",
                borderRadius: "10px",
                border: "1px solid var(--border-subtle)",
                marginBottom: "14px",
              }}
            >
              {[
                { id: "context", label: "🧭 Context Engine", desc: "Why did your portfolio move today?" },
                { id: "risk",    label: "📐 Risk Metrics",    desc: "Vol, beta, Sharpe, correlation" },
                { id: "intel",   label: "🧠 AI Analysis",      desc: "Portfolio health + signals" },
              ].map((t) => {
                const active = aiTab === t.id;
                return (
                  <button
                    key={t.id}
                    type="button"
                    data-tour={t.id === "intel" ? "ai-analysis-tab" : undefined}
                    onClick={() => setAiTab(t.id)}
                    title={t.desc}
                    style={{
                      flex: 1,
                      padding: "10px 12px",
                      borderRadius: "8px",
                      border: "none",
                      background: active ? "var(--color-bg-card)" : "transparent",
                      color: active ? "var(--color-text-primary)" : "var(--color-text-muted)",
                      fontSize: "12px",
                      fontWeight: 700,
                      letterSpacing: "0.01em",
                      cursor: "pointer",
                      transition: "background 0.15s, color 0.15s",
                      boxShadow: active ? "0 1px 0 rgba(255,255,255,0.04) inset" : "none",
                    }}
                  >
                    {t.label}
                  </button>
                );
              })}
            </div>

            <div style={{ display: aiTab === "context" ? "block" : "none" }}>
              <PortfolioContextCard
                positions={portfolio.positions.map((p) => ({ ticker: p.ticker, quantity: p.quantity, buy_price: p.buy_price }))}
              />
            </div>

            <div style={{ display: aiTab === "risk" ? "block" : "none" }}>
              <RiskMetricsCard
                positions={portfolio.positions.map((p) => ({ ticker: p.ticker, quantity: p.quantity, buy_price: p.buy_price }))}
              />
            </div>

            <div style={{ display: aiTab === "intel" ? "block" : "none" }}>

          {!intel && !intelLoading && (
            <AnalysisStandbyCard portfolio={portfolio} onRun={runIntelligence} />
          )}

          {intelLoading && (
            <div style={{ marginBottom: "24px" }}>
              <MissionControlLoader
                steps={intelSteps}
                portfolioSize={portfolio?.positions?.length || 0}
                variant="analysis"
              />
            </div>
          )}

          {intel && (
            <AnalysisResultPanel
              intel={intel}
              onReanalyze={() => { setIntel(null); setIntelSteps([]); runIntelligence(); }}
            />
          )}

            </div>{/* /intel tab */}
          </div>{/* /AI tools panel */}

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

// ---------------------------------------------------------------------------
// AnalysisResultPanel — editorial-aesthetic result view for the AI Analysis
// tab. Replaces the old glass-card grid with emoji headers (🧠 ⚠️ 💡) and
// gradient backgrounds. Same data, restrained typography:
//
//   • Header strip mirrors MissionControlLoader so before/during/after
//     read as the same instrument changing state
//   • Big numeric health score on the left + 4 horizontal breakdown bars
//   • Single-column risk + directions lists, no gradient cards
//   • One accent color (indigo); semantic green/red used only for scores
// ---------------------------------------------------------------------------
function AnalysisResultPanel({ intel, onReanalyze }) {
  const score = intel?.portfolio_health_score;
  const breakdown = intel?.health_breakdown || {};
  const risks = intel?.top_risks || [];
  const directions = intel?.suggested_directions || intel?.recommendations || [];
  const theses = intel?.holding_theses || [];

  const scoreColor =
    score == null
      ? "var(--color-text-muted)"
      : score >= 70
      ? "var(--color-accent-green)"
      : score >= 40
      ? "var(--color-accent-amber)"
      : "var(--color-accent-red)";

  const scoreLabel =
    score == null ? "—" : score >= 70 ? "STRONG" : score >= 40 ? "BALANCED" : "FRAGILE";

  return (
    <div
      style={{
        marginBottom: "24px",
        background: "var(--color-bg-secondary)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-card)",
        padding: "22px 24px 26px",
        fontFamily:
          "var(--font-mono)",
      }}
    >
      {/* Header strip — matches MissionControl + Standby for visual continuity. */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "22px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <span
            style={{
              width: "7px",
              height: "7px",
              borderRadius: "50%",
              background: "var(--color-accent-green)",
              boxShadow: "0 0 6px rgba(46,189,107,0.55)",
            }}
          />
          <span
            style={{
              fontSize: "10.5px",
              fontWeight: 700,
              letterSpacing: "0.14em",
              color: "var(--color-text-secondary)",
            }}
          >
            AI ANALYSIS
          </span>
          <span
            style={{
              fontSize: "10px",
              fontWeight: 700,
              letterSpacing: "0.1em",
              color: "var(--color-accent-green)",
            }}
          >
            · COMPLETE
          </span>
        </div>
        <button
          onClick={onReanalyze}
          style={{
            padding: "6px 12px",
            borderRadius: "var(--radius-control)",
            fontSize: "11px",
            fontWeight: 600,
            letterSpacing: "0.06em",
            border: "1px solid var(--border-subtle)",
            background: "transparent",
            color: "var(--color-text-secondary)",
            cursor: "pointer",
            fontFamily: "var(--font-sans)",
            transition: "border-color 0.15s, color 0.15s",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = "var(--border-strong)";
            e.currentTarget.style.color = "var(--color-text-primary)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = "var(--border-subtle)";
            e.currentTarget.style.color = "var(--color-text-secondary)";
          }}
        >
          Re-analyze
        </button>
      </div>

      {/* SCORE + BREAKDOWN row. Numbers loudest, single horizontal layout
          instead of a 3-up glass-card grid. */}
      <div
        className="analysis-score-row"
        style={{
          display: "grid",
          gridTemplateColumns: "auto 1fr",
          gap: "36px",
          alignItems: "center",
          paddingBottom: "22px",
          borderBottom: "1px dashed rgba(255,255,255,0.06)",
        }}
      >
        {/* Score block — no SVG ring; the number IS the visual. */}
        <div style={{ display: "flex", flexDirection: "column", gap: "4px", minWidth: "130px" }}>
          <span
            style={{
              fontSize: "10px",
              fontWeight: 700,
              letterSpacing: "0.14em",
              color: "var(--color-text-muted)",
            }}
          >
            PORTFOLIO HEALTH
          </span>
          <div style={{ display: "flex", alignItems: "baseline", gap: "6px" }}>
            <span
              style={{
                fontFamily:
                  "var(--font-sans)",
                fontSize: "52px",
                fontWeight: 700,
                lineHeight: 1,
                color: scoreColor,
                letterSpacing: "-0.04em",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {score ?? "—"}
            </span>
            <span
              style={{
                fontSize: "13px",
                color: "var(--color-text-muted)",
                fontWeight: 600,
              }}
            >
              /100
            </span>
          </div>
          <span
            style={{
              fontSize: "10px",
              fontWeight: 700,
              letterSpacing: "0.16em",
              color: scoreColor,
              marginTop: "2px",
            }}
          >
            {scoreLabel}
          </span>
        </div>

        {/* 4 thin breakdown bars. Each is one row: label, ━━━━━░░░ bar, number. */}
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          {["diversification", "quality", "risk", "momentum"].map((key) => {
            const val = breakdown[key];
            const num = typeof val === "number" ? val : null;
            return (
              <div
                key={key}
                style={{
                  display: "grid",
                  gridTemplateColumns: "120px 1fr 48px",
                  alignItems: "center",
                  gap: "14px",
                }}
              >
                <span
                  style={{
                    fontSize: "10.5px",
                    fontWeight: 600,
                    letterSpacing: "0.1em",
                    color: "var(--color-text-muted)",
                    textTransform: "uppercase",
                  }}
                >
                  {key}
                </span>
                <ThinBar value={num} />
                <span
                  style={{
                    fontSize: "12.5px",
                    fontWeight: 700,
                    color: num == null ? "var(--color-text-muted)" : "var(--color-text-primary)",
                    fontVariantNumeric: "tabular-nums",
                    textAlign: "right",
                  }}
                >
                  {num ?? "—"}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* RISKS — left-aligned list, no gradient cards, no emoji. */}
      {risks.length > 0 && (
        <ResultSection title="Concentration & risks" count={risks.length}>
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {risks.map((risk, i) => (
              <div
                key={i}
                style={{
                  display: "grid",
                  gridTemplateColumns: "auto 1fr",
                  gap: "12px",
                  alignItems: "baseline",
                }}
              >
                <span
                  style={{
                    color: "var(--color-accent-red)",
                    fontWeight: 700,
                    fontSize: "12px",
                  }}
                >
                  {String(i + 1).padStart(2, "0")}
                </span>
                <div
                  style={{
                    fontFamily:
                      "var(--font-sans)",
                  }}
                >
                  <div
                    style={{
                      fontSize: "13px",
                      fontWeight: 700,
                      color: "var(--color-text-primary)",
                      marginBottom: "2px",
                    }}
                  >
                    {risk.title}
                  </div>
                  <div
                    title={claimSource(risk.description) || ""}
                    style={{
                      fontSize: "12.5px",
                      color: "var(--color-text-secondary)",
                      lineHeight: 1.5,
                    }}
                  >
                    {claimText(risk.description)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </ResultSection>
      )}

      {/* STRATEGIC DIRECTIONS — same list pattern, conviction tag on the right. */}
      {directions.length > 0 && (
        <ResultSection title="Strategic directions" count={directions.length}>
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {directions.map((rec, i) => {
              const focus = rec.focus || rec.ticker || rec.name || "Direction";
              const conviction = rec.conviction || "MEDIUM";
              const rationale = rec.rationale;
              const conColor =
                conviction === "HIGH"
                  ? "var(--color-accent-green)"
                  : "var(--color-accent-amber)";
              return (
                <div
                  key={i}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "auto 1fr auto",
                    gap: "12px",
                    alignItems: "baseline",
                  }}
                >
                  <span
                    style={{
                      color: "var(--color-accent-primary)",
                      fontWeight: 700,
                      fontSize: "12px",
                    }}
                  >
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <div
                    style={{
                      fontFamily:
                        "var(--font-sans)",
                    }}
                  >
                    <div
                      style={{
                        fontSize: "13px",
                        fontWeight: 700,
                        color: "var(--color-text-primary)",
                        marginBottom: "2px",
                      }}
                    >
                      {focus}
                    </div>
                    <div
                      title={claimSource(rationale) || ""}
                      style={{
                        fontSize: "12.5px",
                        color: "var(--color-text-secondary)",
                        lineHeight: 1.5,
                      }}
                    >
                      {claimText(rationale)}
                    </div>
                  </div>
                  <span
                    style={{
                      alignSelf: "center",
                      padding: "3px 9px",
                      borderRadius: "var(--radius-pill)",
                      fontSize: "9.5px",
                      fontWeight: 700,
                      letterSpacing: "0.12em",
                      color: conColor,
                      border: `1px solid ${conColor}55`,
                      background: `${conColor}11`,
                      fontFamily:
                        "var(--font-mono)",
                    }}
                  >
                    {conviction}
                  </span>
                </div>
              );
            })}
          </div>
        </ResultSection>
      )}

      {/* HOLDING THESES — the meat. One card per top holding, two-column
          BULL / BEAR layout with WATCH triggers below. This is what turns
          AI Analysis from a "score report" into a decision aid. */}
      {theses.length > 0 && (
        <ResultSection title="Holding theses" count={theses.length}>
          <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
            {theses.map((t) => (
              <HoldingThesisCard key={t.ticker} thesis={t} />
            ))}
          </div>
        </ResultSection>
      )}

      {/* Stack the score block + bars on narrow viewports. */}
      <style jsx>{`
        @media (max-width: 640px) {
          .analysis-score-row {
            grid-template-columns: 1fr !important;
            gap: 20px !important;
          }
        }
      `}</style>
    </div>
  );
}

// Thin horizontal bar used in the health breakdown. Single muted track,
// solid accent fill — no animation gimmick.
function ThinBar({ value }) {
  const pct = typeof value === "number" ? Math.max(0, Math.min(100, value)) : 0;
  const color =
    value == null
      ? "var(--color-text-muted)"
      : value >= 70
      ? "var(--color-accent-green)"
      : value >= 40
      ? "var(--color-accent-amber)"
      : "var(--color-accent-red)";
  return (
    <div
      style={{
        height: "4px",
        borderRadius: "2px",
        background: "rgba(255,255,255,0.05)",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          width: `${pct}%`,
          height: "100%",
          background: color,
          transition: "width 0.8s ease-out",
        }}
      />
    </div>
  );
}

// Section wrapper used for both Risks and Directions — keeps the dashed
// divider + ALL-CAPS title-with-count pattern consistent.
function ResultSection({ title, count, children }) {
  return (
    <div
      style={{
        paddingTop: "22px",
        marginTop: "0",
        borderTop: "1px dashed rgba(255,255,255,0.06)",
        marginBottom: "0",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "8px",
          marginBottom: "14px",
        }}
      >
        <span
          style={{
            fontSize: "10.5px",
            fontWeight: 700,
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            color: "var(--color-text-muted)",
          }}
        >
          {title}
        </span>
        <span
          style={{
            fontSize: "10.5px",
            fontWeight: 700,
            color: "var(--color-text-muted)",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          ({count})
        </span>
      </div>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// HoldingThesisCard — the differentiator. One per top holding. Layout:
//
//   ┌────────────────────────────────────────────────────────────┐
//   │  INFY · Infosys                          BULLISH · 72/100  │
//   │  weight 14% · P&L +12.4%                                   │
//   │  ───────────────────────────────────────                   │
//   │  THESIS  Largest Indian IT services exporter…              │
//   │                                                            │
//   │  BULL                          BEAR                        │
//   │  ▸ ROE 31% + rev growth 13%    ▸ Wage inflation 8%         │
//   │  ▸ USD/INR tailwind            ▸ BFSI budgets soft         │
//   │  ▸ AI services up 40% YoY      ▸ PE 22× vs 5y avg 19×      │
//   │                                                            │
//   │  WATCH                                                     │
//   │  ▸ Earnings 14 May; if margin guide < 21% the rerating    │
//   │    thesis flips.                                           │
//   └────────────────────────────────────────────────────────────┘
//
// No emojis, no gradients, no glass-card. Hairline border, two-column grid
// for BULL/BEAR on desktop that stacks on mobile.
// ---------------------------------------------------------------------------
function HoldingThesisCard({ thesis }) {
  const sig = thesis?.signal || "NEUTRAL";
  const conviction = Number(thesis?.conviction ?? 0);
  const bull = thesis?.bull_case || [];
  const bear = thesis?.bear_case || [];
  const watch = thesis?.watch || [];

  const sigColor =
    sig === "BULLISH"
      ? "var(--color-accent-green)"
      : sig === "CAUTIOUS"
      ? "var(--color-accent-red)"
      : "var(--color-accent-amber)";

  return (
    <article
      className="thesis-card"
      style={{
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-card)",
        background: "var(--color-bg-card)",
        padding: "18px 20px",
        display: "flex",
        flexDirection: "column",
        gap: "16px",
        fontFamily: "var(--font-sans)",
      }}
    >
      {/* Header row — ticker on left, verdict pill + conviction on right. */}
      <header
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: "12px",
          flexWrap: "wrap",
        }}
      >
        <div>
          <div
            style={{
              fontSize: "15px",
              fontWeight: 800,
              color: "var(--color-text-primary)",
              letterSpacing: "-0.01em",
              fontFamily:
                "var(--font-mono)",
            }}
          >
            {thesis.ticker}
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <span
            style={{
              padding: "3px 9px",
              borderRadius: "var(--radius-pill)",
              fontSize: "10px",
              fontWeight: 700,
              letterSpacing: "0.14em",
              color: sigColor,
              border: `1px solid ${sigColor}55`,
              background: `${sigColor}11`,
              fontFamily:
                "var(--font-mono)",
            }}
          >
            {sig}
          </span>
          <span
            title="Conviction — 0-100 scale. Below 60 = bull and bear cases nearly tied."
            style={{
              fontSize: "11px",
              fontWeight: 700,
              color: "var(--color-text-secondary)",
              fontVariantNumeric: "tabular-nums",
              fontFamily: "var(--font-mono)",
              letterSpacing: "0.06em",
            }}
          >
            {conviction}/100
          </span>
        </div>
      </header>

      {/* Thesis line — the universal "what is this for" sentence. */}
      {thesis.thesis && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "60px 1fr",
            alignItems: "baseline",
            gap: "12px",
            paddingBottom: "14px",
            borderBottom: "1px dashed rgba(255,255,255,0.06)",
          }}
        >
          <span
            style={{
              fontSize: "9.5px",
              fontWeight: 700,
              letterSpacing: "0.16em",
              color: "var(--color-text-muted)",
              fontFamily: "var(--font-mono)",
            }}
          >
            THESIS
          </span>
          <span
            style={{
              fontSize: "13px",
              color: "var(--color-text-primary)",
              lineHeight: 1.5,
            }}
          >
            {thesis.thesis}
          </span>
        </div>
      )}

      {/* BULL / BEAR — two columns on desktop, stacked on mobile. */}
      <div
        className="thesis-bullbear"
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "22px",
        }}
      >
        <BullBearList kind="bull" items={bull} />
        <BullBearList kind="bear" items={bear} />
      </div>

      {/* WATCH — catalyst triggers. Indigo accent, single column. */}
      {watch.length > 0 && (
        <div
          style={{
            paddingTop: "14px",
            borderTop: "1px dashed rgba(255,255,255,0.06)",
            display: "grid",
            gridTemplateColumns: "60px 1fr",
            alignItems: "start",
            gap: "12px",
          }}
        >
          <span
            style={{
              fontSize: "9.5px",
              fontWeight: 700,
              letterSpacing: "0.16em",
              color: "var(--color-accent-primary)",
              fontFamily: "var(--font-mono)",
            }}
          >
            WATCH
          </span>
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "6px" }}>
            {watch.slice(0, 2).map((w, i) => (
              <li
                key={i}
                title={claimSource(w) || ""}
                style={{
                  fontSize: "12.5px",
                  color: "var(--color-text-secondary)",
                  lineHeight: 1.55,
                  paddingLeft: "14px",
                  position: "relative",
                }}
              >
                <span
                  style={{
                    position: "absolute",
                    left: 0,
                    top: "0.5em",
                    width: "6px",
                    height: "1px",
                    background: "var(--color-accent-primary)",
                  }}
                />
                {claimText(w)}
              </li>
            ))}
          </ul>
        </div>
      )}

      <style jsx>{`
        @media (max-width: 640px) {
          .thesis-bullbear {
            grid-template-columns: 1fr !important;
            gap: 16px !important;
          }
        }
      `}</style>
    </article>
  );
}

// Reusable bullet column for the bull / bear halves of a thesis card.
function BullBearList({ kind, items }) {
  const color =
    kind === "bull" ? "var(--color-accent-green)" : "var(--color-accent-red)";
  const label = kind === "bull" ? "BULL" : "BEAR";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
      <div
        style={{
          fontSize: "9.5px",
          fontWeight: 700,
          letterSpacing: "0.16em",
          color,
          fontFamily: "var(--font-mono)",
        }}
      >
        {label}
      </div>
      {items.length === 0 ? (
        <div
          style={{
            fontSize: "12.5px",
            color: "var(--color-text-muted)",
            fontStyle: "italic",
          }}
        >
          —
        </div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "6px" }}>
          {items.slice(0, 3).map((b, i) => (
            <li
              key={i}
              title={claimSource(b) || ""}
              style={{
                fontSize: "12.5px",
                color: "var(--color-text-secondary)",
                lineHeight: 1.55,
                paddingLeft: "14px",
                position: "relative",
              }}
            >
              <span
                style={{
                  position: "absolute",
                  left: 0,
                  top: "0.55em",
                  width: "6px",
                  height: "1px",
                  background: color,
                }}
              />
              {claimText(b)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// AnalysisStandbyCard — empty state for the AI Analysis tab before the user
// clicks Run. Replaces the old gradient/emoji hero ("🧠 Analyze My Portfolio")
// with a Mission-Control-style "pre-flight check" panel that:
//
//   • shows REAL portfolio stats (holdings, sectors, invested, current value)
//     so the user sees what the engine will actually chew on
//   • lists CONCRETE deliverables (health score, N verdicts, N risks, …) so
//     the value prop isn't "AI insights" handwave
//   • sets time expectation ("Typical · 30-60s") — same honesty as the loader
//
// Matches editorial-terminal design tokens: hairline border, no gradient,
// solid accent button, mono font for category labels.
// ---------------------------------------------------------------------------
function AnalysisStandbyCard({ portfolio, onRun }) {
  const positions = portfolio?.positions || [];
  const holdingsCount = positions.length;
  const sectorsCount = new Set(
    positions.map((p) => p?.sector).filter((s) => s && s !== "—")
  ).size;
  const invested = Number(portfolio?.total_invested || 0);
  const currentValue = Number(portfolio?.current_value || 0);
  const pnlPct = Number(portfolio?.total_pnl_percent || 0);

  const fmtINR = (v) => {
    if (!v) return "—";
    if (v >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`;
    if (v >= 1e5) return `₹${(v / 1e5).toFixed(2)} L`;
    return `₹${Math.round(v).toLocaleString("en-IN")}`;
  };

  const inputs = [
    { label: "HOLDINGS", value: holdingsCount || "—" },
    { label: "SECTORS",  value: sectorsCount || "—" },
    { label: "INVESTED", value: fmtINR(invested) },
    {
      label: "CURRENT VALUE",
      value: fmtINR(currentValue),
      sub: currentValue
        ? `${pnlPct >= 0 ? "+" : ""}${pnlPct.toFixed(2)}%`
        : null,
      subColor:
        pnlPct >= 0 ? "var(--color-accent-green)" : "var(--color-accent-red)",
    },
  ];

  const outputs = [
    "Portfolio health score + 4-axis breakdown",
    "Bull / bear / watch thesis on top 6 holdings",
    "Top 4 concentration & risk flags",
    "3 strategic rebalance directions",
  ];

  const ready = holdingsCount > 0;

  return (
    <div
      style={{
        marginBottom: "24px",
        background: "var(--color-bg-secondary)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-card)",
        padding: "22px 24px",
        fontFamily:
          "var(--font-mono)",
      }}
    >
      {/* Header strip — mirrors MissionControlLoader so this feels like the
          "before" state of the same instrument. */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "18px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <span
            style={{
              width: "7px",
              height: "7px",
              borderRadius: "50%",
              background: ready
                ? "var(--color-accent-primary)"
                : "var(--color-text-muted)",
              boxShadow: ready ? "0 0 6px rgba(99,102,241,0.6)" : "none",
            }}
          />
          <span
            style={{
              fontSize: "10.5px",
              fontWeight: 700,
              letterSpacing: "0.14em",
              color: "var(--color-text-secondary)",
            }}
          >
            AI ANALYSIS
          </span>
          <span
            style={{
              fontSize: "10px",
              fontWeight: 700,
              letterSpacing: "0.1em",
              color: ready
                ? "var(--color-accent-primary)"
                : "var(--color-text-muted)",
            }}
          >
            · STANDBY
          </span>
        </div>
        <span
          style={{
            fontSize: "10px",
            fontWeight: 700,
            letterSpacing: "0.12em",
            color: ready
              ? "var(--color-accent-green)"
              : "var(--color-text-muted)",
          }}
        >
          {ready ? "READY" : "NO HOLDINGS"}
        </span>
      </div>

      {/* Two-column body — inputs left, outputs right. */}
      <div
        className="standby-cols"
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "32px",
          paddingBottom: "20px",
          borderBottom: "1px dashed rgba(255,255,255,0.06)",
        }}
      >
        <div>
          <div
            style={{
              fontSize: "10px",
              fontWeight: 700,
              letterSpacing: "0.14em",
              color: "var(--color-text-muted)",
              marginBottom: "12px",
            }}
          >
            YOUR PORTFOLIO
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "9px" }}>
            {inputs.map((row) => (
              <div
                key={row.label}
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr auto",
                  alignItems: "baseline",
                  gap: "10px",
                }}
              >
                <span
                  style={{
                    fontSize: "10.5px",
                    fontWeight: 600,
                    letterSpacing: "0.1em",
                    color: "var(--color-text-muted)",
                  }}
                >
                  {row.label}
                </span>
                <span
                  style={{
                    fontSize: "14px",
                    fontWeight: 700,
                    color: "var(--color-text-primary)",
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {row.value}
                  {row.sub && (
                    <span
                      style={{
                        marginLeft: "8px",
                        fontSize: "11px",
                        fontWeight: 600,
                        color: row.subColor,
                      }}
                    >
                      {row.sub}
                    </span>
                  )}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div>
          <div
            style={{
              fontSize: "10px",
              fontWeight: 700,
              letterSpacing: "0.14em",
              color: "var(--color-text-muted)",
              marginBottom: "12px",
            }}
          >
            OUTPUT YOU&apos;LL GET
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "9px" }}>
            {outputs.map((line) => (
              <div
                key={line}
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  gap: "10px",
                  fontSize: "12.5px",
                  color: "var(--color-text-secondary)",
                  fontFamily:
                    "var(--font-sans)",
                }}
              >
                <span style={{ color: "var(--color-accent-primary)", fontWeight: 700 }}>›</span>
                <span>{line}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Action row — solid accent button, no emoji, no gradient. */}
      <div
        style={{
          marginTop: "20px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "16px",
          flexWrap: "wrap",
        }}
      >
        <button
          onClick={onRun}
          disabled={!ready}
          style={{
            padding: "11px 22px",
            borderRadius: "var(--radius-control)",
            fontSize: "13px",
            fontWeight: 700,
            border: ready
              ? "1px solid var(--color-accent-primary)"
              : "1px solid var(--border-subtle)",
            background: ready
              ? "var(--color-accent-primary)"
              : "var(--color-bg-card-hover)",
            color: ready ? "#fff" : "var(--color-text-muted)",
            cursor: ready ? "pointer" : "not-allowed",
            letterSpacing: "0.02em",
            transition: "filter 0.15s",
            fontFamily:
              "var(--font-sans)",
          }}
          onMouseEnter={(e) => {
            if (ready) e.currentTarget.style.filter = "brightness(1.12)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.filter = "none";
          }}
        >
          Run analysis &nbsp;→
        </button>
        <span
          style={{
            fontSize: "11px",
            fontWeight: 600,
            letterSpacing: "0.08em",
            color: "var(--color-text-muted)",
          }}
        >
          TYPICAL &nbsp;·&nbsp; 40–80s
        </span>
      </div>

      {/* Stack the two columns on narrow viewports so labels don't truncate. */}
      <style jsx>{`
        @media (max-width: 560px) {
          .standby-cols {
            grid-template-columns: 1fr !important;
            gap: 22px !important;
          }
        }
      `}</style>
    </div>
  );
}
