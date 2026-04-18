import { useState } from "react";

import { API_BASE as _SHARED_API_BASE } from "../lib/api";
const API_BASE = _SHARED_API_BASE;

export default function AnalysisSimulator({ ticker, stockName }) {
  const [scenario, setScenario] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleSimulate = async () => {
    if (!scenario.trim()) return;
    setLoading(true);
    setResult(null);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/api/analysis/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker, scenario }),
      });

      if (!res.ok) throw new Error("Simulation failed");
      const data = await res.json();
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass-card animate-fade-in" style={{ padding: "24px" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "20px" }}>
        <div>
          <h3 style={{ fontSize: "16px", fontWeight: 700, color: "var(--color-text-primary)", display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ fontSize: "20px" }}>🔮</span> "What-If" Scenario Simulator
          </h3>
          <p style={{ fontSize: "13px", color: "var(--color-text-muted)", marginTop: "4px" }}>
            Test hypothetical macro or idiosyncratic shocks on {stockName}'s fundamentals.
          </p>
        </div>
      </div>

      <div className="simulator-row" style={{ marginBottom: "24px" }}>
        <input
          type="text"
          placeholder="e.g., Crude oil hits $100/bbl, or RBI cuts rates by 50 bps..."
          value={scenario}
          onChange={(e) => setScenario(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSimulate()}
          disabled={loading}
          style={{
            flex: 1, padding: "12px 16px", borderRadius: "10px", fontSize: "14px",
            border: "1px solid var(--border-subtle)", outline: "none",
            background: "rgba(0,0,0,0.2)", color: "var(--color-text-primary)"
          }}
        />
        <button
          onClick={handleSimulate}
          disabled={loading || !scenario.trim()}
          style={{
            minWidth: "140px", padding: "0 20px", borderRadius: "10px", fontSize: "14px", fontWeight: 600,
            background: loading ? "var(--color-bg-tertiary)" : "linear-gradient(135deg, var(--color-accent-primary), var(--color-accent-cyan))",
            color: loading ? "var(--color-text-muted)" : "white", border: "none", cursor: loading || !scenario.trim() ? "not-allowed" : "pointer",
            transition: "all 0.2s ease", position: "relative", overflow: "hidden"
          }}
        >
          {loading ? (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "8px" }}>
              <div className="spinner" style={{ width: "16px", height: "16px", border: "2px solid var(--color-text-muted)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }}></div>
              Simulating...
            </div>
          ) : "Run Simulation"}
        </button>
      </div>

      {error && <div style={{ color: "var(--color-accent-red)", fontSize: "13px", padding: "12px", background: "rgba(239,68,68,0.1)", borderRadius: "8px" }}>{error}</div>}

      {result && (
        <div className="animate-fade-up" style={{ background: "rgba(255,255,255,0.02)", border: "1px solid var(--border-subtle)", borderRadius: "12px", padding: "20px" }}>
          
          <div style={{ display: "flex", alignItems: "flex-start", gap: "24px", marginBottom: "20px", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "20px" }}>
            
            <div style={{ flex: 1 }}>
              <h4 style={{ fontSize: "12px", textTransform: "uppercase", letterSpacing: "1px", color: "var(--color-text-muted)", marginBottom: "8px", fontWeight: 600 }}>Estimated Impact</h4>
              <div style={{ display: "flex", alignItems: "baseline", gap: "12px" }}>
                <span style={{ 
                  fontSize: "42px", fontWeight: 700, letterSpacing: "-1px",
                  color: result.impact.score_percent > 0 ? "var(--color-accent-green)" : result.impact.score_percent < 0 ? "var(--color-accent-red)" : "var(--color-text-primary)" 
                }}>
                  {result.impact.score_percent > 0 ? "+" : ""}{result.impact.score_percent}%
                </span>
                <span style={{ 
                  padding: "4px 10px", borderRadius: "6px", fontSize: "12px", fontWeight: 600,
                  background: result.impact.severity === "High" ? "rgba(239,68,68,0.15)" : result.impact.severity === "Medium" ? "rgba(245,158,11,0.15)" : "rgba(16,185,129,0.15)",
                  color: result.impact.severity === "High" ? "var(--color-accent-red)" : result.impact.severity === "Medium" ? "#F59E0B" : "var(--color-accent-green)" 
                }}>
                  {result.impact.severity} Risk
                </span>
              </div>
            </div>

            <div style={{ display: "flex", gap: "16px", background: "rgba(0,0,0,0.2)", padding: "16px", borderRadius: "10px", minWidth: "220px" }}>
               <div style={{ flex: 1 }}>
                 <span style={{ display: "block", fontSize: "11px", color: "var(--color-text-muted)", marginBottom: "4px" }}>Rev Impact</span>
                 <span style={{ fontSize: "16px", fontWeight: 600, color: "var(--color-text-primary)" }}>{result.adjusted_metrics.revenue_estimate_change}</span>
               </div>
               <div style={{ width: "1px", background: "var(--border-subtle)" }}></div>
               <div style={{ flex: 1 }}>
                 <span style={{ display: "block", fontSize: "11px", color: "var(--color-text-muted)", marginBottom: "4px" }}>Margin Shift</span>
                 <span style={{ fontSize: "16px", fontWeight: 600, color: "var(--color-text-primary)" }}>{result.adjusted_metrics.margin_impact_bps} bps</span>
               </div>
            </div>

          </div>

          <div>
             <h4 style={{ fontSize: "12px", textTransform: "uppercase", letterSpacing: "1px", color: "var(--color-text-muted)", marginBottom: "12px", fontWeight: 600 }}>Causal Rationale</h4>
             <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "10px" }}>
               {result.rationale.map((line, idx) => (
                 <li key={idx} style={{ fontSize: "14px", color: "var(--color-text-secondary)", display: "flex", gap: "12px", lineHeight: 1.5 }}>
                   <span style={{ color: "var(--color-accent-primary)" }}>•</span>
                   {line}
                 </li>
               ))}
             </ul>
          </div>
        </div>
      )}

      {/* Internal spinner animation style */}
      <style dangerouslySetInnerHTML={{__html: `
        @keyframes spin { 100% { transform: rotate(360deg); } }
      `}} />
    </div>
  );
}
