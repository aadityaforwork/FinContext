"use client";

import { useState } from "react";
import { API_BASE as _SHARED_API_BASE } from "../lib/api";
import { claimText, claimSource } from "../lib/claim";

const API_BASE = _SHARED_API_BASE;

// ---------- Display helpers ----------
// Numeric API outputs use fractions (0.196 = 19.6%). UI shows percent for vol /
// drawdown / HHI; raw numbers for beta / Sharpe.
function fmtPct(v, digits = 1) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}
function fmtNum(v, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return Number(v).toFixed(digits);
}

// Color thresholds — chosen so green/amber/red match the existing PortfolioView palette.
function colorVol(v) {
  if (v === null || v === undefined) return "var(--color-text-muted)";
  if (v < 0.15) return "var(--color-accent-green)";
  if (v < 0.25) return "#f59e0b";
  return "var(--color-accent-red)";
}
function colorBeta(v) {
  if (v === null || v === undefined) return "var(--color-text-muted)";
  if (v < 0.8) return "var(--color-accent-cyan)";       // defensive
  if (v <= 1.2) return "var(--color-accent-green)";     // market-like
  return "var(--color-accent-red)";                     // aggressive
}
function colorSharpe(v) {
  if (v === null || v === undefined) return "var(--color-text-muted)";
  if (v >= 1) return "var(--color-accent-green)";
  if (v >= 0) return "#f59e0b";
  return "var(--color-accent-red)";
}
function colorDrawdown(v) {
  if (v === null || v === undefined) return "var(--color-text-muted)";
  if (v > -0.15) return "var(--color-accent-green)";
  if (v > -0.30) return "#f59e0b";
  return "var(--color-accent-red)";
}
function colorHHI(v) {
  if (v === null || v === undefined) return "var(--color-text-muted)";
  if (v < 0.25) return "var(--color-accent-green)";
  if (v < 0.5) return "#f59e0b";
  return "var(--color-accent-red)";
}

// ---------- Component ----------
export default function RiskMetricsCard({ positions }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const run = async () => {
    if (!positions?.length) return;
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const res = await fetch(`${API_BASE}/api/risk/metrics`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ positions }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Request failed: ${res.status}`);
      }
      setData(await res.json());
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass-card animate-fade-in" style={{ padding: "24px", marginBottom: "20px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "16px", flexWrap: "wrap" }}>
        <div>
          <h3 style={{ fontSize: "16px", fontWeight: 700, color: "var(--color-text-primary)", display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ fontSize: "20px" }}>📐</span> Risk Metrics
          </h3>
          <p style={{ fontSize: "13px", color: "var(--color-text-muted)", marginTop: "4px", maxWidth: "580px" }}>
            Volatility, beta vs NIFTY 50, drawdowns, Sharpe, sector concentration, and pairwise correlation — computed from 5 years of daily price history.
          </p>
        </div>
        {!data && !loading && (
          <button onClick={run} disabled={!positions?.length}
            style={{
              padding: "10px 18px", borderRadius: "10px", fontSize: "13px", fontWeight: 600,
              background: positions?.length ? "linear-gradient(135deg, var(--color-accent-primary), var(--color-accent-cyan))" : "var(--color-bg-tertiary)",
              color: positions?.length ? "white" : "var(--color-text-muted)",
              border: "none", cursor: positions?.length ? "pointer" : "not-allowed",
            }}>
            Compute Risk Metrics
          </button>
        )}
        {data && (
          <button onClick={run}
            style={{
              padding: "6px 12px", borderRadius: "8px", fontSize: "12px",
              border: "1px solid var(--border-subtle)", background: "transparent",
              color: "var(--color-text-muted)", cursor: "pointer",
            }}>
            ↻ Recompute
          </button>
        )}
      </div>

      {error && (
        <div style={{ marginTop: "14px", color: "var(--color-accent-red)", fontSize: "13px", padding: "10px", background: "rgba(239,68,68,0.08)", borderRadius: "8px" }}>
          {error}
        </div>
      )}

      {loading && (
        <div style={{ marginTop: "16px", display: "flex", alignItems: "center", gap: "12px", padding: "14px 16px", background: "rgba(99,102,241,0.06)", border: "1px solid rgba(99,102,241,0.18)", borderRadius: "10px" }}>
          <div className="shimmer" style={{ width: "18px", height: "18px", borderRadius: "50%" }} />
          <span style={{ fontSize: "13px", color: "var(--color-text-secondary)" }}>
            Fetching 5y price history for every holding + NIFTY 50, building returns matrix, computing metrics...
          </span>
        </div>
      )}

      {data && <ResultsBlock data={data} />}
    </div>
  );
}

// ---------- Results sub-tree ----------
function ResultsBlock({ data }) {
  const m = data.metrics || {};
  const c = data.concentration || {};
  const corr = data.correlations || {};
  const expl = data.explanation || {};

  const heroTiles = [
    { label: "Volatility (annualized)", value: fmtPct(m.volatility_annualized), color: colorVol(m.volatility_annualized), source: "metrics.volatility_annualized" },
    { label: "Beta vs NIFTY 50",        value: fmtNum(m.beta_vs_nifty50, 2),    color: colorBeta(m.beta_vs_nifty50),     source: "metrics.beta_vs_nifty50" },
    { label: "Sharpe ratio",            value: fmtNum(m.sharpe_ratio, 2),       color: colorSharpe(m.sharpe_ratio),      source: `metrics.sharpe_ratio (rf=${(m.risk_free_rate_used ?? 0.06) * 100}%)` },
    { label: "Max drawdown 1Y",         value: fmtPct(m.max_drawdown_1y),       color: colorDrawdown(m.max_drawdown_1y), source: "metrics.max_drawdown_1y" },
  ];

  const drawdowns = [
    { label: "1Y", value: m.max_drawdown_1y },
    { label: "3Y", value: m.max_drawdown_3y },
    { label: "5Y", value: m.max_drawdown_5y },
  ];

  return (
    <div style={{ marginTop: "20px", display: "flex", flexDirection: "column", gap: "20px" }}>
      {/* Hero metric tiles */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "12px" }}>
        {heroTiles.map((t) => (
          <div key={t.label} title={t.source}
            style={{ padding: "14px 16px", background: "rgba(0,0,0,0.2)", borderRadius: "10px" }}>
            <div style={{ fontSize: "10px", color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "1px" }}>{t.label}</div>
            <div style={{ fontSize: "22px", fontWeight: 800, color: t.color, marginTop: "4px", fontVariantNumeric: "tabular-nums" }}>
              {t.value}
            </div>
          </div>
        ))}
      </div>

      {/* Concentration row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "12px" }}>
        <div style={{ padding: "16px", border: "1px solid var(--border-subtle)", borderRadius: "12px" }}>
          <div style={{ fontSize: "11px", color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "1px", marginBottom: "8px" }}>Sector HHI</div>
          <div style={{ fontSize: "26px", fontWeight: 800, color: colorHHI(c.sector_hhi), fontVariantNumeric: "tabular-nums" }}>
            {fmtNum(c.sector_hhi, 2)}
          </div>
          <div style={{ fontSize: "11px", color: "var(--color-text-muted)", marginTop: "4px" }}>1.00 = single sector · &lt;0.25 = diversified</div>
        </div>
        <ConcTile label="Top holding share" value={c.top_holding_pct} />
        <ConcTile label="Top 3 holdings share" value={c.top_3_holdings_pct} />
        <ConcTile label="Largest sector share" value={c.top_sector_pct} />
      </div>

      {/* Drawdown horizon strip */}
      <div style={{ padding: "16px", border: "1px solid var(--border-subtle)", borderRadius: "12px" }}>
        <div style={{ fontSize: "11px", color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "1px", marginBottom: "12px" }}>Max drawdown by horizon</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "12px" }}>
          {drawdowns.map((d) => (
            <div key={d.label}>
              <div style={{ fontSize: "10px", color: "var(--color-text-muted)" }}>{d.label}</div>
              <div style={{ fontSize: "18px", fontWeight: 700, color: colorDrawdown(d.value), fontVariantNumeric: "tabular-nums" }}>
                {fmtPct(d.value)}
              </div>
            </div>
          ))}
        </div>
        <div style={{ fontSize: "11px", color: "var(--color-text-muted)", marginTop: "10px" }}>
          Sample size: {m.sample_size_days ?? 0} trading days · risk-free rate used: {((m.risk_free_rate_used ?? 0.06) * 100).toFixed(1)}%
        </div>
      </div>

      {/* Flagged correlation clusters */}
      {(c.flagged_clusters?.length > 0 || (corr.high_correlation_pairs || []).length > 0) && (
        <div style={{ padding: "16px", border: "1px solid var(--border-subtle)", borderRadius: "12px" }}>
          <div style={{ fontSize: "11px", color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "1px", marginBottom: "12px" }}>
            Hidden concentration (correlation ≥ 0.75)
          </div>
          {c.flagged_clusters?.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {c.flagged_clusters.map((line, i) => (
                <div key={i} style={{ fontSize: "13px", color: "var(--color-text-secondary)", padding: "8px 12px", background: "rgba(245,158,11,0.06)", borderLeft: "3px solid #f59e0b", borderRadius: "8px" }}>
                  {line}
                </div>
              ))}
            </div>
          ) : (
            <div style={{ fontSize: "13px", color: "var(--color-text-muted)" }}>
              No holding pairs above the 0.75 correlation threshold.
            </div>
          )}
        </div>
      )}

      {/* Agent narration (or deterministic fallback) */}
      {expl?.summary && (
        <div style={{ padding: "16px", border: "1px solid var(--border-subtle)", borderRadius: "12px", background: "rgba(99,102,241,0.04)" }}>
          <div style={{ fontSize: "11px", fontWeight: 700, color: "var(--color-accent-primary)", textTransform: "uppercase", letterSpacing: "1px", marginBottom: "10px" }}>
            🧠 Risk Brief
          </div>
          <p style={{ fontSize: "14px", fontWeight: 600, color: "var(--color-text-primary)", marginBottom: "12px", lineHeight: 1.5 }}>
            {expl.summary}
          </p>
          {expl.observations?.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: "6px", marginBottom: "12px" }}>
              {expl.observations.map((o, i) => (
                <div key={i} title={claimSource(o) || ""} style={{ fontSize: "13px", color: "var(--color-text-secondary)", lineHeight: 1.5, paddingLeft: "12px", borderLeft: "2px solid rgba(99,102,241,0.4)" }}>
                  {claimText(o)}
                </div>
              ))}
            </div>
          )}
          {expl.risks?.length > 0 && (
            <div style={{ marginTop: "10px" }}>
              <div style={{ fontSize: "10px", fontWeight: 700, color: "var(--color-accent-red)", textTransform: "uppercase", letterSpacing: "1px", marginBottom: "6px" }}>
                ⚠️ Risks worth flagging
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                {expl.risks.map((r, i) => (
                  <div key={i} title={claimSource(r) || ""} style={{ fontSize: "13px", color: "var(--color-text-secondary)", lineHeight: 1.5, padding: "8px 12px", background: "rgba(239,68,68,0.06)", borderLeft: "3px solid var(--color-accent-red)", borderRadius: "8px" }}>
                    {claimText(r)}
                  </div>
                ))}
              </div>
            </div>
          )}
          <FooterMeta confidence={expl.confidence} data_gaps={expl.data_gaps} />
        </div>
      )}

      {/* Disclaimer (Phase 1 contract) */}
      {data.disclaimer && (
        <div style={{ fontSize: "11px", color: "var(--color-text-muted)", lineHeight: 1.5, padding: "10px 12px", background: "rgba(0,0,0,0.15)", borderRadius: "8px" }}>
          <strong style={{ color: "var(--color-text-secondary)" }}>Disclaimer:</strong> {data.disclaimer}
        </div>
      )}
    </div>
  );
}

function ConcTile({ label, value }) {
  const v = value;
  const color = v == null ? "var(--color-text-muted)"
    : v >= 50 ? "var(--color-accent-red)"
    : v >= 30 ? "#f59e0b"
    : "var(--color-accent-green)";
  return (
    <div style={{ padding: "16px", border: "1px solid var(--border-subtle)", borderRadius: "12px" }}>
      <div style={{ fontSize: "11px", color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "1px", marginBottom: "8px" }}>{label}</div>
      <div style={{ fontSize: "26px", fontWeight: 800, color, fontVariantNumeric: "tabular-nums" }}>
        {v == null ? "—" : `${v.toFixed(1)}%`}
      </div>
    </div>
  );
}

function FooterMeta({ confidence, data_gaps }) {
  if (!confidence && (!data_gaps || data_gaps.length === 0)) return null;
  return (
    <div style={{ marginTop: "12px", padding: "8px 12px", background: "rgba(0,0,0,0.18)", borderRadius: "8px", display: "flex", flexWrap: "wrap", gap: "12px", alignItems: "center" }}>
      {confidence && (
        <span style={{ fontSize: "11px", fontWeight: 700, color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "1px" }}>
          Confidence: <span style={{ color: confidence === "high" ? "var(--color-accent-green)" : confidence === "medium" ? "#f59e0b" : "var(--color-accent-red)" }}>{confidence}</span>
        </span>
      )}
      {data_gaps?.length > 0 && (
        <span style={{ fontSize: "11px", color: "var(--color-text-muted)" }}>
          Gaps: {data_gaps.slice(0, 3).join(" · ")}{data_gaps.length > 3 ? ` (+${data_gaps.length - 3} more)` : ""}
        </span>
      )}
    </div>
  );
}
